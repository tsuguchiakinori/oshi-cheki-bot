from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

app = Flask(__name__)

# ←ここにさっきのやつ貼る
CHANNEL_ACCESS_TOKEN = "EecvJy3p8FakrBHR+YSq/DD3MgCyVqVOQTBPKaa498vy8K/zvXWC6TCuh5zWL8Z0lhn4FE90x7agy/oP6FLv0cxvQLW4oK6fEqELMU0pdbsOgRaBsKouFT6w+QO0UdwwySuRyTpzjxKjyDnf/7kXRwdB04t89/1O/w1cDnyilFU="
CHANNEL_SECRET = "38b1bd16322ce948e132554848286444"

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_message = event.message.text

    # 👇ここ自由にいじれる
    if "チェキ" in user_message:
        reply = "推しチェキいいね！📸✨"
    else:
        reply = f"{user_message} って言ったね！"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply)
    )

import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
