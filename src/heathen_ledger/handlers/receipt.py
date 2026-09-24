"""Handlers for scanning, itemizing, and interactively splitting receipt photos."""

import contextlib
import html
import logging
from telegram import Update
from telegram.constants import ChatType
from telegram.ext import ContextTypes
from sqlalchemy.orm import Session

from ..database import with_db_session
from ..repositories import GroupRepository, UserRepository
from ..telegram import TelegramRichClient
from ..keyboards.ticket import TicketKeyboardBuilder
from ..models import User
from .common import send_response
from .voice import is_bot_mentioned
from ..receipt import get_receipt_parser
from ..services import ReceiptService

logger = logging.getLogger(__name__)


def is_image_media(message) -> bool:
    """Check if message contains a photo or image document."""
    if not message:
        return False
    if getattr(message, "photo", None):
        return True
    if getattr(message, "document", None) and getattr(
        message.document, "mime_type", ""
    ).startswith("image/"):
        return True
    return False


async def process_receipt_media(
    media_message,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int | None = None,
) -> None:
    """Process receipt image from media_message, create session, and send interactive rich message."""
    if not is_image_media(media_message):
        return

    # Check if receipt parser can be instantiated (GEMINI_API_KEY check)
    try:
        get_receipt_parser()
    except ValueError:
        await send_response(
            update,
            context,
            "⚠️ Receipt photo received, but `GEMINI_API_KEY` is not configured.\n"
            "Please set `GEMINI_API_KEY` in your `.env` to enable receipt OCR scanning.",
        )
        return

    if chat_id is None:
        target_chat = getattr(update, "effective_chat", None)
        if target_chat and hasattr(target_chat, "id"):
            chat_id = target_chat.id

    try:
        receipt, formatted_text = await ReceiptService.process_receipt_image(
            bot=context.bot,
            media_message=media_message,
            chat_id=chat_id,
        )
        if not receipt.items:
            await send_response(
                update,
                context,
                formatted_text,
                parse_mode="Markdown",
            )
            return

        user = getattr(update, "effective_user", None)
        creator_id = user.id if user else None
        creator_name = user.first_name if user else "Member"

        session = ReceiptService.create_ticket_session(
            chat_id=chat_id,
            creator_id=creator_id,
            creator_name=creator_name,
            receipt=receipt,
        )
        rich_html, keyboard = ReceiptService.build_ticket_rich_message(session.token)
        await send_response(
            update,
            context,
            rich_html=rich_html,
            reply_markup=keyboard,
            ephemeral=False,
        )
    except Exception as e:
        logger.exception("Failed to process receipt image with Gemini")
        await send_response(
            update,
            context,
            f"❌ Failed to parse receipt image: {e}",
            parse_mode="Markdown",
        )


async def ticket_command_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /ticket or /receipt command: process captioned photo or replied-to photo."""
    if not update.message:
        return

    # Case 1: The command message itself has a photo
    if is_image_media(update.message):
        chat_id = update.effective_chat.id if update.effective_chat else None
        return await process_receipt_media(
            media_message=update.message,
            update=update,
            context=context,
            chat_id=chat_id,
        )

    # Case 2: Replied to a message containing a photo
    reply_to = update.message.reply_to_message
    if reply_to and is_image_media(reply_to):
        chat_id = update.effective_chat.id if update.effective_chat else None
        return await process_receipt_media(
            media_message=reply_to,
            update=update,
            context=context,
            chat_id=chat_id,
        )

    # Case 3: No photo attached or replied to
    await send_response(
        update,
        context,
        "💡 To parse a receipt, reply to a photo with `/ticket` or send a photo with the caption `/ticket`.",
        parse_mode="Markdown",
    )


async def ticket_photo_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle incoming photos: auto-process in private DMs or if caption has command/mention."""
    if not update.message or not is_image_media(update.message):
        return

    chat = update.effective_chat
    is_private = chat is not None and chat.type == ChatType.PRIVATE

    if is_private:
        chat_id = chat.id if chat else None
        return await process_receipt_media(
            media_message=update.message,
            update=update,
            context=context,
            chat_id=chat_id,
        )

    caption = (update.message.caption or "").strip()
    has_command = caption.lower().startswith(("/ticket", "/receipt"))
    has_mention = await is_bot_mentioned(update, context)

    if has_command or has_mention:
        chat_id = chat.id if chat else None
        return await process_receipt_media(
            media_message=update.message,
            update=update,
            context=context,
            chat_id=chat_id,
        )


async def ticket_mention_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle replies mentioning the bot when replied-to message is an image."""
    if not update.message:
        return

    reply_to = update.message.reply_to_message
    if not reply_to or not is_image_media(reply_to):
        return

    if not await is_bot_mentioned(update, context):
        return

    chat_id = update.effective_chat.id if update.effective_chat else None
    await process_receipt_media(
        media_message=reply_to,
        update=update,
        context=context,
        chat_id=chat_id,
    )


@with_db_session
async def ticket_callback_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session
) -> None:
    """Handle callback queries for ticket interactive claiming and splitting."""
    query = update.callback_query
    if not query or not query.data:
        return

    data = query.data
    parts = data.split(":")
    action = parts[1] if len(parts) > 1 else ""

    # tkt:m:<token>:<item_idx>
    if action == "m" and len(parts) >= 4:
        token = parts[2]
        try:
            item_idx = int(parts[3])
        except ValueError:
            return

        user = query.from_user
        s, added = ReceiptService.toggle_item_me(
            token=token,
            item_idx=item_idx,
            user_id=user.id,
            display_name=user.first_name,
            username=user.username,
            last_name=user.last_name,
        )
        if not s:
            await query.answer("⚠️ This ticket session has expired.", show_alert=True)
            return

        rich_html, kb = ReceiptService.build_ticket_rich_message(token)
        await TelegramRichClient.edit_rich_message_or_ephemeral(
            query=query,
            bot=context.bot,
            rich_html=rich_html or "",
            reply_markup=kb,
        )
        status_str = "Claimed" if added else "Unclaimed"
        await query.answer(f"{status_str} item #{item_idx + 1}")
        return

    # tkt:d:<token>:<item_idx>
    elif action == "d" and len(parts) >= 4:
        token = parts[2]
        try:
            item_idx = int(parts[3])
        except ValueError:
            return

        s, done = ReceiptService.toggle_item_done(token, item_idx)
        if not s:
            await query.answer("⚠️ This ticket session has expired.", show_alert=True)
            return

        rich_html, kb = ReceiptService.build_ticket_rich_message(token)
        await TelegramRichClient.edit_rich_message_or_ephemeral(
            query=query,
            bot=context.bot,
            rich_html=rich_html or "",
            reply_markup=kb,
        )
        await query.answer(f"Item #{item_idx + 1} marked {'done' if done else 'open'}")
        return

    # tkt:asgn:<token>
    elif action == "asgn" and len(parts) >= 3:
        token = parts[2]
        rich_html, kb = ReceiptService.build_person_selector_message(
            token=token, db_session=session
        )
        if not rich_html or not kb:
            await query.answer("⚠️ This ticket session has expired.", show_alert=True)
            return

        await TelegramRichClient.edit_rich_message_or_ephemeral(
            query=query,
            bot=context.bot,
            rich_html=rich_html,
            reply_markup=kb,
        )
        await query.answer()
        return

    # tkt:psel:<token>:<participant_key>
    elif action == "psel" and len(parts) >= 4:
        token = parts[2]
        participant_key = ":".join(parts[3:])
        rich_html, kb = ReceiptService.build_person_checklist_message(
            token=token, participant_key=participant_key
        )
        if not rich_html or not kb:
            await query.answer("⚠️ This ticket session has expired.", show_alert=True)
            return

        await TelegramRichClient.edit_rich_message_or_ephemeral(
            query=query,
            bot=context.bot,
            rich_html=rich_html,
            reply_markup=kb,
        )
        await query.answer()
        return

    # tkt:ptog:<token>:<participant_key>:<item_idx>
    elif action == "ptog" and len(parts) >= 5:
        token = parts[2]
        try:
            item_idx = int(parts[-1])
        except ValueError:
            return
        participant_key = ":".join(parts[3:-1])

        # If it's a tg user, resolve their display name from db
        participant_obj = None
        if participant_key.startswith("tg:"):
            try:
                tg_uid = int(participant_key.split(":")[1])
                u = UserRepository(session).get_by_telegram_id(tg_uid)
                if not u:
                    u = session.query(User).filter(User.id == tg_uid).first()
                if u:
                    from ..receipt.pending_store import (
                        extract_initials,
                        TicketParticipant,
                    )

                    first_name = getattr(u, "first_name", "") or f"User {tg_uid}"
                    last_name = getattr(u, "last_name", None)
                    username = getattr(u, "username", None)
                    participant_obj = TicketParticipant(
                        participant_key=participant_key,
                        display_name=first_name,
                        initials=extract_initials(first_name, last_name, username),
                        user_id=getattr(u, "telegram_id", tg_uid),
                        username=username,
                        is_external=False,
                    )
            except Exception as e:
                logger.warning("Failed to resolve participant_obj: %s", e)

        s, added = ReceiptService.toggle_participant_item(
            token=token,
            participant_key=participant_key,
            item_idx=item_idx,
            participant=participant_obj,
        )
        if not s:
            await query.answer("⚠️ This ticket session has expired.", show_alert=True)
            return

        p_name = participant_obj.display_name if participant_obj else None
        rich_html, kb = ReceiptService.build_person_checklist_message(
            token=token,
            participant_key=participant_key,
            participant_name=p_name,
        )
        await TelegramRichClient.edit_rich_message_or_ephemeral(
            query=query,
            bot=context.bot,
            rich_html=rich_html or "",
            reply_markup=kb,
        )
        status_text = "Claimed" if added else "Unclaimed"
        await query.answer(f"{status_text} item #{item_idx + 1}")
        return

    # tkt:asgn_itm:<token>:<item_idx>
    elif action == "asgn_itm" and len(parts) >= 4:
        token = parts[2]
        try:
            item_idx = int(parts[3])
        except ValueError:
            return

        s = ReceiptService.get_session(token)
        if not s:
            await query.answer("⚠️ This ticket session has expired.", show_alert=True)
            return

        chat = getattr(query.message, "chat", None)
        chat_id = chat.id if chat else None
        members = []
        if chat_id:
            group = GroupRepository(session).get_by_telegram_id(chat_id)
            if group and group.members:
                members = group.members

        it_name = s.items[item_idx].name if item_idx < len(s.items) else "Item"
        kb = TicketKeyboardBuilder.build_member_selector_keyboard(
            token=token,
            item_idx=item_idx,
            members=members,
            item_name=it_name,
        )
        safe_name = html.escape(it_name)
        rich_html = (
            f"<p>🧾 <b>Assign Member to Item #{item_idx + 1}:</b> <i>{safe_name}</i></p>"
            f"<p>Tap a member to toggle their claim, or add an external name:</p>"
        )
        await TelegramRichClient.edit_rich_message_or_ephemeral(
            query=query,
            bot=context.bot,
            rich_html=rich_html,
            reply_markup=kb,
        )
        await query.answer()
        return

    # tkt:asgn_usr:<token>:<item_idx>:<user_id>
    elif action == "asgn_usr" and len(parts) >= 5:
        token = parts[2]
        try:
            item_idx = int(parts[3])
            user_id = int(parts[4])
        except ValueError:
            return

        s = ReceiptService.get_session(token)
        if not s:
            await query.answer("⚠️ This ticket session has expired.", show_alert=True)
            return

        u = UserRepository(session).get_by_telegram_id(user_id)
        if not u:
            u = session.query(User).filter(User.id == user_id).first()

        display_name = u.first_name if u else f"User {user_id}"
        username = u.username if u else None

        ReceiptService.assign_group_member(
            token=token,
            item_idx=item_idx,
            user_id=user_id,
            display_name=display_name,
            username=username,
        )
        rich_html, kb = ReceiptService.build_ticket_rich_message(token)
        await TelegramRichClient.edit_rich_message_or_ephemeral(
            query=query,
            bot=context.bot,
            rich_html=rich_html or "",
            reply_markup=kb,
        )
        await query.answer(f"Updated {display_name} on item #{item_idx + 1}")
        return

    # tkt:asgn_new:<token>[:<item_idx>]
    elif action == "asgn_new" and len(parts) >= 3:
        token = parts[2]
        item_idx = None
        if len(parts) >= 4:
            with contextlib.suppress(ValueError):
                item_idx = int(parts[3])

        s = ReceiptService.get_session(token)
        if not s:
            await query.answer("⚠️ This ticket session has expired.", show_alert=True)
            return

        chat = getattr(query.message, "chat", None)
        chat_id = chat.id if chat else None
        msg_id = getattr(query.message, "message_id", None)
        context.user_data["pending_ext_ticket"] = {
            "token": token,
            "item_idx": item_idx,
            "chat_id": chat_id,
            "message_id": msg_id,
        }
        prompt_suffix = ""
        if item_idx is not None and item_idx < len(s.items):
            prompt_suffix = f" for *{s.items[item_idx].name}*"
        if query.message:
            await query.message.reply_text(
                f"Please send the name of the external guest{prompt_suffix}:\n(or send `/cancel` to abort)",
                parse_mode="Markdown",
            )
        await query.answer()
        return

    # tkt:fin:<token>
    elif action == "fin" and len(parts) >= 3:
        token = parts[2]
        s = ReceiptService.get_session(token)
        if not s:
            await query.answer("⚠️ This ticket session has expired.", show_alert=True)
            return

        (
            summary_md,
            kb_split,
            shares,
            rich_html,
        ) = ReceiptService.build_split_summary_message(token)
        if not shares:
            await query.answer(
                "⚠️ No items have been claimed yet! Tap [+Me] on your items first.",
                show_alert=True,
            )
            return

        await TelegramRichClient.edit_rich_message_or_ephemeral(
            query=query,
            bot=context.bot,
            rich_html=rich_html or "",
            reply_markup=kb_split,
        )
        await query.answer()
        return

    # tkt:record:<token>
    elif action == "record" and len(parts) >= 3:
        token = parts[2]
        user = query.from_user
        chat = getattr(query.message, "chat", None)
        chat_id = chat.id if chat else query.from_user.id
        chat_title = getattr(chat, "title", None)

        try:
            text, reply_markup = ReceiptService.record_ticket_expense(
                token=token,
                db_session=session,
                payer_id=user.id,
                payer_username=user.username,
                payer_first_name=user.first_name,
                chat_id=chat_id,
                chat_title=chat_title,
            )
            if query.message:
                await query.edit_message_text(
                    text=text,
                    parse_mode="Markdown",
                    reply_markup=reply_markup,
                )
            await query.answer("✅ Expense recorded in group ledger!")
        except Exception as e:
            logger.exception("Failed to record ticket expense")
            await query.answer(f"❌ Error: {e}", show_alert=True)
        return

    # tkt:back:<token>
    elif action == "back" and len(parts) >= 3:
        token = parts[2]
        rich_html, kb = ReceiptService.build_ticket_rich_message(token)
        if not rich_html:
            await query.answer("⚠️ This ticket session has expired.", show_alert=True)
            return

        await TelegramRichClient.edit_rich_message_or_ephemeral(
            query=query,
            bot=context.bot,
            rich_html=rich_html,
            reply_markup=kb,
        )
        await query.answer()
        return

    # tkt:cancel:<token>
    elif action == "cancel" and len(parts) >= 3:
        token = parts[2]
        ReceiptService.pop_session(token)
        if query.message:
            await query.edit_message_text("❌ Ticket splitting cancelled.")
        await query.answer("Ticket cancelled.")
        return


async def ticket_external_reply_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle text input when a user submits an external participant name."""
    if not update.message or not update.message.text:
        return

    pending = context.user_data.get("pending_ext_ticket")
    if not pending:
        return

    name = update.message.text.strip()
    if name.startswith("/") and name.lower() in (
        "/cancel",
        "/cancel@heathenledgerbot",
    ):
        context.user_data.pop("pending_ext_ticket", None)
        await update.message.reply_text("Cancelled adding external participant.")
        return

    token = pending["token"]
    item_idx = pending.get("item_idx")
    chat_id = pending.get("chat_id")
    message_id = pending.get("message_id")
    context.user_data.pop("pending_ext_ticket", None)

    s, p = ReceiptService.register_external_participant(token, name)
    if not s or not p:
        await update.message.reply_text("⚠️ This ticket session has expired.")
        return

    # If an item index was specified (legacy item-first flow), also assign it
    if item_idx is not None and 0 <= item_idx < len(s.items):
        s.items[item_idx].participants[p.participant_key] = p

    # Update original ticket message to show the checklist for this participant!
    if chat_id and message_id:
        rich_html, kb = ReceiptService.build_person_checklist_message(
            token=token,
            participant_key=p.participant_key,
            participant_name=p.display_name,
        )
        if rich_html and kb:
            try:
                await TelegramRichClient.edit_rich_message_text(
                    bot=context.bot,
                    chat_id=chat_id,
                    message_id=message_id,
                    rich_html=rich_html,
                    reply_markup=kb,
                )
            except Exception as e:
                logger.warning(
                    "Could not edit ticket message after external assignment: %s",
                    e,
                )

    await update.message.reply_text(
        f"✅ Registered guest *{name}*!\nTap the items above to select what they took part in, then tap *Done*.",
        parse_mode="Markdown",
    )
