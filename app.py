import os
import time
import random
import hashlib
import math
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


def fit_text(draw, text, max_width, start_size=74, min_size=38):
    size = start_size
    while size >= min_size:
        font = load_font(size)
        bbox = draw.textbbox((0, 0), text, font=font)
        if (bbox[2] - bbox[0]) <= max_width:
            return font
        size -= 4
    return load_font(min_size)


def add_vignette(img, strength=0.28):
    w, h = img.size
    mask = Image.new("L", (w, h), 0)
    px = mask.load()

    cx, cy = w / 2, h / 2
    max_dist = math.sqrt(cx**2 + cy**2)

    for y in range(h):
        for x in range(w):
            dist = math.sqrt((x - cx)**2 + (y - cy)**2)
            px[x, y] = int(255 * (dist / max_dist)**1.8 * strength)

    dark = Image.new("RGB", (w, h), (40, 32, 24))
    return Image.composite(dark, img, mask)


def apply_old_cheki_photo_filter(img):
    # ③ 写真の色味を少しランダム化
    color = random.uniform(0.70, 0.78)
    contrast = random.uniform(1.02, 1.08)
    brightness = random.uniform(0.94, 0.99)

    img = ImageEnhance.Color(img).enhance(color)
    img = ImageEnhance.Contrast(img).enhance(contrast)
    img = ImageEnhance.Brightness(img).enhance(brightness)

    warm = Image.new("RGB", img.size, (255, 232, 195))
    img = Image.blend(img, warm, random.uniform(0.14, 0.18))

    sepia = Image.new("RGB", img.size, (120, 82, 50))
    img = Image.blend(img, sepia, random.uniform(0.02, 0.04))

    noise = Image.effect_noise(img.size, random.randint(12, 18)).convert("RGB")
    img = Image.blend(img, noise, random.uniform(0.035, 0.05))

    img = add_vignette(img, strength=random.uniform(0.24, 0.30))
    img = img.filter(ImageFilter.GaussianBlur(random.uniform(0.08, 0.14)))

    return img


def draw_soft_stain(base, x, y, rx, ry, color, alpha):
    stain = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(stain)

    d.ellipse(
        (x - rx, y - ry, x + rx, y + ry),
        fill=(color[0], color[1], color[2], alpha)
    )

    stain = stain.filter(ImageFilter.GaussianBlur(random.randint(10, 24)))
    return Image.alpha_composite(base.convert("RGBA"), stain).convert("RGB")


def make_old_paper_frame(width, height):
    base = Image.new("RGB", (width, height), "#f3eddf")

    warm = Image.new("RGB", (width, height), (255, 239, 210))
    base = Image.blend(base, warm, 0.26)

    noise = Image.effect_noise((width, height), 22).convert("RGB")
    base = Image.blend(base, noise, 0.045)

    # ① 汚れの確率制御
    # 70% 控えめ / 20% 強め / 10% ほぼなし
    r = random.random()
    if r < 0.70:
        stain_count = random.randint(1, 3)
        stain_alpha = random.randint(16, 28)
        stain_size = (18, 55)
    elif r < 0.90:
        stain_count = random.randint(3, 6)
        stain_alpha = random.randint(22, 38)
        stain_size = (28, 85)
    else:
        stain_count = random.randint(0, 1)
        stain_alpha = random.randint(10, 18)
        stain_size = (12, 35)

    # ② 自然な汚れ：丸ではなく楕円＋ぼかし
    for _ in range(stain_count):
        x = random.randint(-30, width + 30)
        y = random.randint(-30, height + 30)
        rx = random.randint(stain_size[0], stain_size[1])
        ry = random.randint(stain_size[0] // 2, stain_size[1])
        color = random.choice([
            (190, 178, 150),
            (205, 192, 165),
            (175, 160, 132),
            (220, 206, 180),
        ])
        base = draw_soft_stain(base, x, y, rx, ry, color, stain_alpha)

    # 端のくすみ
    edge = Image.new("L", (width, height), 0)
    px = edge.load()

    for y in range(height):
        for x in range(width):
            d = min(x, width - x, y, height - y)
            v = max(0, 1 - d / 220)
            px[x, y] = int(255 * (v ** 1.8) * 0.22)

    aged = Image.new("RGB", (width, height), (214, 202, 180))
    base = Image.composite(aged, base, edge)

    # 下余白にうっすら経年感
    gradient = Image.new("L", (1, height))
    for y in range(height):
        gradient.putpixel((0, y), int(255 * (y / height) ** 2 * 0.12))

    alpha = gradient.resize((width, height))
    shade = Image.new("RGB", (width, height), (222, 213, 196))
    base = Image.composite(shade, base, alpha)

    return base


def round_corners(img, radius=18):
    img = img.convert("RGBA")
    mask = Image.new("L", img.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, img.size[0], img.size[1]), radius, fill=255)
    img.putalpha(mask)
    return img


def draw_hand_text(base_img, text, x, y, font):
    draw = ImageDraw.Draw(base_img)
    current_x = x

    for char in text:
        bbox = draw.textbbox((0, 0), char, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]

        char_img = Image.new("RGBA", (w + 40, h + 40), (0, 0, 0, 0))
        char_draw = ImageDraw.Draw(char_img)
        char_draw.text((20, 20), char, font=font, fill=(30, 30, 30))

        char_img = char_img.rotate(random.uniform(-2, 2), resample=Image.BICUBIC, expand=True)

        base_img.paste(
            char_img,
            (int(current_x + random.randint(-2, 2)), int(y + random.randint(-3, 3))),
            char_img
        )

        current_x += w + random.randint(4, 7)


def make_cheki(user_id):
    key = user_key(user_id)

    img = Image.open(f"/tmp/input_{key}.jpg").convert("RGB")

    w, h = img.size
    size = min(w, h)
    img = img.crop(((w - size) // 2, (h - size) // 2, (w + size) // 2, (h + size) // 2))
    img = img.resize((900, 900))
    img = apply_old_cheki_photo_filter(img)
    img = round_corners(img, radius=18)

    frame = make_old_paper_frame(1000, 1300)

    # 写真位置をわずかにズラして整いすぎを避ける
    photo_x = 50 + random.randint(-5, 5)
    photo_y = 80 + random.randint(-4, 4)
    frame.paste(img, (photo_x, photo_y), img)

    draw = ImageDraw.Draw(frame)

    text = user_texts.get(user_id, "")
    date = user_dates.get(user_id, "")

    font = fit_text(draw, text, 820)
    date_font = load_font(42)

    bbox = draw.textbbox((0, 0), text, font=font)
    text_x = (1000 - (bbox[2] - bbox[0])) // 2 + random.randint(-15, 15)

    draw_hand_text(frame, text, text_x, 1030 + random.randint(-4, 6), font)

    if date:
        bbox = draw.textbbox((0, 0), date, font=date_font)
        date_x = (1000 - (bbox[2] - bbox[0])) // 2 + random.randint(-10, 10)
        draw.text((date_x, 1130 + random.randint(-2, 5)), date, fill=(100, 100, 100), font=date_font)

    # 最後に全体へごく薄い粒子
    final_noise = Image.effect_noise(frame.size, 10).convert("RGB")
    frame = Image.blend(frame, final_noise, 0.016)

    frame.save(f"/tmp/output_{key}.jpg", quality=95)
    return key


@app.route("/")
def home():
    return "OK"


@app.route("/output/<key>.jpg")
def output(key):
    return send_file(f"/tmp/output_{key}.jpg", mimetype="image/jpeg")


@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
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

    if user_states.get(user_id) == "text":
        user_texts[user_id] = msg
        user_states[user_id] = "date"

        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="日付を送って！（不要なら「なし」）")
        )
        return

    if user_states.get(user_id) == "date":
        user_dates[user_id] = "" if msg in ["なし", "無し", "不要", "いらない"] else msg

        key = make_cheki(user_id)
        image_url = f"{BASE_URL}/output/{key}.jpg?{int(time.time())}"

        line_bot_api.reply_message(
            event.reply_token,
            ImageSendMessage(
                original_content_url=image_url,
                preview_image_url=image_url
            )
        )

        user_states[user_id] = None
        return

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text="まず画像を送ってね📸")
    )
