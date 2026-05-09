import sqlite3
import datetime
from typing import List, Dict, Optional

DB_PATH = 'ledger.db'

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes the database and creates tables if they don't exist."""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Track which users are in which chat
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chat_users (
                chat_id INTEGER,
                username TEXT,
                PRIMARY KEY (chat_id, username)
            )
        ''')
        
        # Track expenses
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                payer_username TEXT,
                amount REAL,
                description TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Track how much each participant owes for a specific expense
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS expense_splits (
                expense_id INTEGER,
                username TEXT,
                amount_owed REAL,
                FOREIGN KEY (expense_id) REFERENCES expenses (id) ON DELETE CASCADE,
                PRIMARY KEY (expense_id, username)
            )
        ''')
        
        conn.commit()

def track_user(chat_id: int, username: str):
    """Tracks a user as being part of a chat."""
    if not username:
        return
    # Ensure usernames start with @ for consistency
    if not username.startswith('@'):
        username = f"@{username}"
        
    with get_connection() as conn:
        conn.cursor().execute('''
            INSERT OR IGNORE INTO chat_users (chat_id, username)
            VALUES (?, ?)
        ''', (chat_id, username))
        conn.commit()

def get_chat_users(chat_id: int) -> List[str]:
    """Returns a list of all known usernames in a chat."""
    with get_connection() as conn:
        cursor = conn.cursor().execute('''
            SELECT username FROM chat_users WHERE chat_id = ?
        ''', (chat_id,))
        return [row['username'] for row in cursor.fetchall()]

def add_expense(chat_id: int, payer_username: str, amount: float, description: str, participants: Optional[List[str]] = None):
    """
    Adds an expense. If participants is empty or None, splits equally among all known chat users.
    Ensures that payer_username is tracked as part of the chat.
    """
    track_user(chat_id, payer_username)
    
    if not participants:
        participants = get_chat_users(chat_id)
        if not participants:
            # Fallback if no one is known (shouldn't happen since payer is tracked)
            participants = [payer_username]
            
    # Normalize participant usernames
    participants = [p if p.startswith('@') else f"@{p}" for p in participants]
    
    # Track all participants in the chat as well
    for p in participants:
        track_user(chat_id, p)
        
    split_amount = amount / len(participants)
    
    with get_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO expenses (chat_id, payer_username, amount, description)
            VALUES (?, ?, ?, ?)
        ''', (chat_id, payer_username, amount, description))
        
        expense_id = cursor.lastrowid
        
        splits = [(expense_id, p, split_amount) for p in participants]
        cursor.executemany('''
            INSERT INTO expense_splits (expense_id, username, amount_owed)
            VALUES (?, ?, ?)
        ''', splits)
        
        conn.commit()

def get_balances(chat_id: int) -> Dict[str, float]:
    """
    Calculates the net balance for each user in the chat.
    Positive means they are owed money. Negative means they owe money.
    """
    balances = {}
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Calculate how much each user has paid in total
        cursor.execute('''
            SELECT payer_username, SUM(amount) as total_paid
            FROM expenses
            WHERE chat_id = ?
            GROUP BY payer_username
        ''', (chat_id,))
        
        for row in cursor.fetchall():
            balances[row['payer_username']] = balances.get(row['payer_username'], 0) + row['total_paid']
            
        # Calculate how much each user owes in total
        cursor.execute('''
            SELECT es.username, SUM(es.amount_owed) as total_owed
            FROM expense_splits es
            JOIN expenses e ON es.expense_id = e.id
            WHERE e.chat_id = ?
            GROUP BY es.username
        ''', (chat_id,))
        
        for row in cursor.fetchall():
            username = row['username']
            balances[username] = balances.get(username, 0) - row['total_owed']
            
    # Filter out near-zero balances due to floating point inaccuracies
    return {user: round(balance, 2) for user, balance in balances.items() if abs(round(balance, 2)) > 0}

def clear_expenses(chat_id: int):
    """Clears all expenses and splits for a chat when settled."""
    with get_connection() as conn:
        conn.cursor().execute('''
            DELETE FROM expenses WHERE chat_id = ?
            -- SQLite handles cascading deletes for expense_splits if PRAGMA foreign_keys = ON is set,
            -- but just to be safe if PRAGMA is off, we delete directly or configure it.
        ''', (chat_id,))
        conn.commit()
