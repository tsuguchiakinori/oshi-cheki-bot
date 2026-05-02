import os
import time
import random
import hashlib
from flask import Flask, request, abort, send_file
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent,
    TextMessage,
    ImageMessage,
    TextSendMessage,
    ImageSendMessage,
)
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter

app = Flask(__name__)

CHANNEL_ACCESS_TOKEN = os.environ["CHANNEL_ACCESS_TOKEN"]
CHANNEL_SECRET = os.environ["CHANNEL_SECRET"]
BASE_URL = "https://oshi-cheki-bot.onrender.com"

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

user_states = {}
user_texts = {}
user_dates = {}


def user_key(user_id):
    return hashlib.md5(user_id.encode()).hexdigest()


def load_font(size):
    try:
        return ImageFont.truetype("makiirclehand.ttf", size)
    except:
        return ImageFont.load_default()


def fit_text(draw, text, max_width, start_size=70, min_size=34):
    size = start_size
    while size >= min_size:
        font = load_font(size)
        bbox = draw.textbbox((0, 0), text, font=font)
        width = bbox[2] - bbox[0]
        if width <= max_width:
            return font
        size -= 4
    return load_font(min_size)


def apply_cheki_filter(img):
    img = ImageEnhance.Color(img).enhance(0.9)
    img = ImageEnhance.Contrast(img).enhance(1.08)
    img = ImageEnhance.Brightness(img).enhance(1.04)

    warm = Image.new("RGB", img.size, (255, 246, 230))
    img = Image.blend(img, warm, 0.08)

    img = img.filter(ImageFilter.GaussianBlur(0.25))
    return img


def make_cheki(user_id):
    key = user_key(user_id)
    input_path = f"/tmp/input_{key}.jpg"
    output_path = f"/tmp/output_{key}.jpg"

    text = user_texts.get(user_id, "My Oshi")
    date = user_dates.get(user_id, "")

    img = Image.open(input_path).convert("RGB")

    w, h = img.size
    size = min(w, h)
    img = img.crop(((w - size) // 2, (h - size) // 2, (w + size) // 2, (h + size) // 2))
    img = img.resize((900, 900))
    img = apply_cheki_filter(img)

    frame = Image.new("RGB", (1000, 1300), "#f7f5f2")
    frame.paste(img, (50, 80))

    draw = ImageDraw.Draw(frame)

    text_font = fit_text(draw, text, 840, 74, 38)
    date_font = load_font(42)

    text_bbox = draw.textbbox((0, 0), text, font=text_font)
    text_w = text_bbox[2] - text_bbox[0]
    text_x = (1000 - text_w) // 2

    draw.text((text_x, 1030), text, fill=(35, 35, 35), font=text_font)

    if date:
        date_bbox = draw.textbbox((0, 0), date, font=date_font)
        date_w = date_bbox[2] - date_bbox[0]
        date_x = (1000 - date_w) // 2
        draw.text((date_x, 1130), date, fill=(110, 110, 110), font=date_font)

    shadow = frame.filter(ImageFilter.GaussianBlur(8))
    final = Image.new("RGB", (1040, 1340), "#e5e3df")
    final.paste(shadow, (20, 20))
    final.paste(frame, (0, 0))

    final.save(output_path, quality=95)
    return key


@app.route("/", methods=["GET"])
def home():
    return "OK"


@app.route("/output/<key>.jpg", methods=["GET"])
def output_image(key):
    return send_file(f"/tmp/output_{key}.jpg", mimetype="image/jpeg")


@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return "OK"


@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    user_id = event.source.user_id
    key = user_key(user_id)

    message_content = line_bot_api.get_message_content(event.message.id)

    with open(f"/tmp/input_{key}.jpg", "wb") as f:
        for chunk in message_content.iter_content():
            f.write(chunk)

    user_states[user_id] = "waiting_text"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text="画像受け取ったで📸\n下に入れる文字を送って！")
    )


@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    user_id = event.source.user_id
    msg = event.message.text.strip()
    state = user_states.get(user_id)

    if state == "waiting_text":
        user_texts[user_id] = msg
        user_states[user_id] = "waiting_date"

        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=f"文字を設定したで📸\n「{msg}」\n次に日付を送って！不要なら「なし」")
        )
        return

    if state == "waiting_date":
        if msg in ["なし", "無し", "いらない", "不要"]:
            user_dates[user_id] = ""
        else:
            user_dates[user_id] = msg

        key = make_cheki(user_id)
        image_url = f"{BASE_URL}/output/{key}.jpg?v={int(time.time())}"

        user_states[user_id] = None

        line_bot_api.reply_message(
            event.reply_token,
            ImageSendMessage(
                original_content_url=image_url,
                preview_image_url=image_url
            )
        )
        return

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text="まず画像を送ってね📸")
    )
