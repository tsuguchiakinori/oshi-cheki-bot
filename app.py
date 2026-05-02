import os
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage, ImageSendMessage
import requests
from PIL import Image

app = Flask(__name__)

# 環境変数
CHANNEL_ACCESS_TOKEN = os.environ["CHANNEL_ACCESS_TOKEN"]
CHANNEL_SECRET = os.environ["CHANNEL_SECRET"]

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


# -----------------------
# テキスト返信
# -----------------------
@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    user_message = event.message.text

    if "チェキ" in user_message:
        reply = "写真送ってくれたらチェキにするで📸"
    else:
        reply = f"{user_message} って言ったね！"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply)
    )


# -----------------------
# 画像受信 → チェキ化
# -----------------------
@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):

    # ① LINEから画像取得
    message_content = line_bot_api.get_message_content(event.message.id)

    with open("input.jpg", "wb") as f:
        for chunk in message_content.iter_content():
            f.write(chunk)

    # ② チェキ風加工
    img = Image.open("input.jpg").convert("RGB")

    # サイズ調整（正方形）
    size = min(img.size)
    img = img.crop((0, 0, size, size))
    img = img.resize((800, 800))

    # 白フレーム作成（チェキ）
    frame = Image.new("RGB", (900, 1100), "white")
    frame.paste(img, (50, 50))

    # 保存
    frame.save("output.jpg")

    # ③ 画像を一時アップロード（超簡易：imgur代替なしで返す用）
    # 👉 RenderではローカルURL使えないので、暫定でdataURL化
    import base64
    with open("output.jpg", "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    image_url = f"data:image/jpeg;base64,{b64}"

    # ④ LINE返信
    line_bot_api.reply_message(
        event.reply_token,
        ImageSendMessage(
            original_content_url=image_url,
            preview_image_url=image_url
        )
    )
