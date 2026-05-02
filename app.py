import os
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

app = Flask(__name__)

CHANNEL_ACCESS_TOKEN = os.environ["EecvJy3p8FakrBHR+YSq/DD3MgCyVqVOQTBPKaa498vy8K/zvXWC6TCuh5zWL8Z0lhn4FE90x7agy/oP6FLv0cxvQLW4oK6fEqELMU0pdbsOgRaBsKouFT6w+QO0UdwwySuRyTpzjxKjyDnf/7kXRwdB04t89/1O/w1cDnyilFU="]
CHANNEL_SECRET = os.environ["38b1bd16322ce948e132554848286444"]

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

@app.route("/", methods=["GET"])
def home():
    return "OK"

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return "OK"

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_message = event.message.text

    if "チェキ" in user_message:
        reply = "推しチェキいいね！📸✨"
    else:
        reply = f"{user_message} って言ったね！"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply)
    )
