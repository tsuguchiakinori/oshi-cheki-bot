# --- 追加import ---
from linebot.models import (
    QuickReply, QuickReplyButton, MessageAction
)

MAX_TEXT_LENGTH = 14


def send_quick_reply(token, text):
    line_bot_api.reply_message(
        token,
        TextSendMessage(
            text=text,
            quick_reply=QuickReply(items=[
                QuickReplyButton(action=MessageAction(label="もう一回つくる", text="やり直し")),
                QuickReplyButton(action=MessageAction(label="文字だけ変える", text="文字変更")),
                QuickReplyButton(action=MessageAction(label="日付だけ変える", text="日付変更")),
            ])
        )
    )


def send_date_quick_reply(token):
    today = time.strftime("%Y.%m.%d")

    line_bot_api.reply_message(
        token,
        TextSendMessage(
            text="日付を送って！（不要ならボタン👇）",
            quick_reply=QuickReply(items=[
                QuickReplyButton(action=MessageAction(label="今日", text=today)),
                QuickReplyButton(action=MessageAction(label="なし", text="なし")),
            ])
        )
    )


@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    user_id = event.source.user_id
    key = user_key(user_id)

    content = line_bot_api.get_message_content(event.message.id)

    with open(f"/tmp/input_{key}.jpg", "wb") as f:
        for chunk in content.iter_content():
            f.write(chunk)

    user_states[user_id] = "text"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text="下に入れる文字を送って！")
    )


@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    user_id = event.source.user_id
    msg = event.message.text.strip()

    # --- UX操作 ---
    if msg == "やり直し":
        user_states[user_id] = None
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="もう一度画像を送ってね📸")
        )
        return

    if msg == "文字変更":
        user_states[user_id] = "text"
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="新しい文字を送って！")
        )
        return

    if msg == "日付変更":
        user_states[user_id] = "date"
        send_date_quick_reply(event.reply_token)
        return

    # --- 文字入力 ---
    if user_states.get(user_id) == "text":

        if len(msg) > MAX_TEXT_LENGTH:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"文字は{MAX_TEXT_LENGTH}文字までにして🙏")
            )
            return

        user_texts[user_id] = msg
        user_states[user_id] = "date"

        send_date_quick_reply(event.reply_token)
        return

    # --- 日付入力 ---
    if user_states.get(user_id) == "date":

        user_dates[user_id] = "" if msg == "なし" else msg

        # ローディング
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="いい感じに現像中…📸")
        )

        key = make_cheki(user_id)
        image_url = f"{BASE_URL}/output/{key}.jpg?{int(time.time())}"

        # 画像送信＋ボタン
        line_bot_api.push_message(
            user_id,
            ImageSendMessage(
                original_content_url=image_url,
                preview_image_url=image_url
            )
        )

        send_quick_reply(user_id, "どうする？")

        user_states[user_id] = None
        return

    # fallback
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text="まず画像を送ってね📸")
    )
