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


def fit_text(draw, text, max_width, start_size=76, min_size=40):
    size = start_size
    while size >= min_size:
        font = load_font(size)
        bbox = draw.textbbox((0, 0), text, font=font)
        width = bbox[2] - bbox[0]
        if width <= max_width:
            return font
        size -= 4
    return load_font(min_size)


def apply_photo_filter(img):
    img = ImageEnhance.Color(img).enhance(0.84)
    img = ImageEnhance.Contrast(img).enhance(0.98)
    img = ImageEnhance.Brightness(img).enhance(1.06)

    warm = Image.new("RGB", img.size, (255, 244, 224))
    img = Image.blend(img, warm, 0.10)

    noise = Image.effect_noise(img.size, 6).convert("RGB")
    img = Image.blend(img, noise, 0.035)

    img = img.filter(ImageFilter.GaussianBlur(0.15))
    return img


def make_paper_frame(width, height):
    base = Image.new("RGB", (width, height), "#f7f3ea")

    # 紙の黄ばみ
    warm = Image.new("RGB", (width, height), (255, 247, 230))
    base = Image.blend(base, warm, 0.22)

    # 紙の細かい粒子
    noise = Image.effect_noise((width, height), 14).convert("RGB")
    base = Image.blend(base, noise, 0.035)

    # 下余白に少しだけ濃淡を出す
    gradient = Image.new("L", (1, height))
    for y in range(height):
        value = int(255 * (y / height) * 0.10)
        gradient.putpixel((0, y), value)

    alpha = gradient.resize((width, height))
    shade = Image.new("RGB", (width, height), (232, 226, 214))
    base = Image.composite(shade, base, alpha)

    return base


def draw_hand_text(base_img, text, x, y, font, fill=(35, 35, 35), spacing=4):
    draw = ImageDraw.Draw(base_img)
    current_x = x

    for char in text:
        bbox = draw.textbbox((0, 0), char, font=font)
        char_w = bbox[2] - bbox[0]
        char_h = bbox[3] - bbox[1]

        char_img = Image.new("RGBA", (char_w + 40, char_h + 40), (0, 0, 0, 0))
        char_draw = ImageDraw.Draw(char_img)
        char_draw.text((20, 20), char, font=font, fill=fill)

        angle = random.uniform(-1.6, 1.6)
        char_img = char_img.rotate(angle, resample=Image.BICUBIC, expand=True)

        offset_x = random.randint(-1, 1)
        offset_y = random.randint(-2, 2)

        base_img.paste(char_img, (int(current_x + offset_x), int(y + offset_y)), char_img)

        current_x += char_w + spacing + random.randint(0, 2)


def make_cheki(user_id):
    key = user_key(user_id)
    input_path = f"/tmp/input_{key}.jpg"
    output_path = f"/tmp/output_{key}.jpg"

    text = user_texts.get(user_id, "My Oshi")
    date = user_dates.get(user_id, "")

    img = Image.open(input_path).convert("RGB")

    # 正方形トリミング
    w, h = img.size
    size = min(w, h)
    img = img.crop(((w - size) // 2, (h - size) // 2, (w + size) // 2, (h + size) // 2))
    img = img.resize((900, 900))
    img = apply_photo_filter(img)

    # チェキ本体だけ生成
    frame = make_paper_frame(1000, 1300)

    # 写真部分
    frame.paste(img, (50, 80))

    draw = ImageDraw.Draw(frame)

    text_font = fit_text(draw, text, max_width=840, start_size=76, min_size=40)
    date_font = load_font(42)

    # メインテキスト
    text_bbox = draw.textbbox((0, 0), text, font=text_font)
    text_w = text_bbox[2] - text_bbox[0]
    text_x = (1000 - text_w) // 2

    draw_hand_text(frame, text, text_x, 1030, text_font, fill=(35, 35, 35), spacing=4)

    # 日付
    if date:
        date_bbox = draw.textbbox((0, 0), date, font=date_font)
        date_w = date_bbox[2] - date_bbox[0]
        date_x = (1000 - date_w) // 2
        draw.text((date_x, 1130), date, fill=(105, 105, 100), font=date_font)

    frame.save(output_path, quality=95)
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
        user_dates[user_id] = "" if msg in ["なし", "無し", "いらない", "不要"] else msg

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
