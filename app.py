import os
import time
import random
import hashlib
import math
from datetime import datetime, timedelta

from flask import Flask, request, abort, send_file
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent,
    TextMessage,
    ImageMessage,
    TextSendMessage,
    ImageSendMessage,
    QuickReply,
    QuickReplyButton,
    MessageAction,
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

MAX_TEXT_LENGTH = 14


def user_key(user_id):
    return hashlib.md5(user_id.encode()).hexdigest()


def load_font(size):
    try:
        return ImageFont.truetype("makiirclehand.ttf", size)
    except Exception:
        return ImageFont.load_default()


def fit_text(draw, text, max_width, start_size=None, min_size=38):
    if start_size is None:
        if len(text) <= 6:
            start_size = 88
        elif len(text) <= 10:
            start_size = 80
        else:
            start_size = 74

    size = start_size
    while size >= min_size:
        font = load_font(size)
        bbox = draw.textbbox((0, 0), text, font=font)
        if (bbox[2] - bbox[0]) <= max_width:
            return font
        size -= 4
    return load_font(min_size)


def add_vignette(img, strength=0.22):
    w, h = img.size
    mask = Image.new("L", (w, h), 0)
    px = mask.load()

    cx, cy = w / 2, h / 2
    max_dist = math.sqrt(cx**2 + cy**2)

    for y in range(h):
        for x in range(w):
            dist = math.sqrt((x - cx) ** 2 + (y - cy) ** 2)
            px[x, y] = int(255 * (dist / max_dist) ** 1.8 * strength)

    dark = Image.new("RGB", (w, h), (45, 36, 28))
    return Image.composite(dark, img, mask)


def apply_old_cheki_photo_filter(img):
    img = ImageEnhance.Color(img).enhance(random.uniform(0.76, 0.84))
    img = ImageEnhance.Contrast(img).enhance(random.uniform(1.04, 1.10))
    img = ImageEnhance.Brightness(img).enhance(random.uniform(1.00, 1.05))

    warm = Image.new("RGB", img.size, (255, 234, 202))
    img = Image.blend(img, warm, random.uniform(0.10, 0.14))

    sepia = Image.new("RGB", img.size, (120, 82, 50))
    img = Image.blend(img, sepia, random.uniform(0.015, 0.03))

    noise = Image.effect_noise(img.size, random.randint(10, 15)).convert("RGB")
    img = Image.blend(img, noise, random.uniform(0.025, 0.04))

    img = add_vignette(img, strength=random.uniform(0.18, 0.24))
    img = img.filter(ImageFilter.GaussianBlur(random.uniform(0.06, 0.10)))

    return img


def draw_soft_stain(base, x, y, rx, ry, color, alpha, blur=18):
    stain = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(stain)
    d.ellipse((x - rx, y - ry, x + rx, y + ry), fill=(color[0], color[1], color[2], alpha))
    stain = stain.filter(ImageFilter.GaussianBlur(blur))
    return Image.alpha_composite(base.convert("RGBA"), stain).convert("RGB")


def add_edge_and_bottom_stains(base, width, height):
    edge_count = random.randint(3, 7)

    for _ in range(edge_count):
        side = random.choice(["left", "right", "top", "bottom"])

        if side == "left":
            x = random.randint(-40, 45)
            y = random.randint(0, height)
        elif side == "right":
            x = random.randint(width - 45, width + 40)
            y = random.randint(0, height)
        elif side == "top":
            x = random.randint(0, width)
            y = random.randint(-35, 45)
        else:
            x = random.randint(0, width)
            y = random.randint(height - 220, height + 30)

        rx = random.randint(18, 65)
        ry = random.randint(10, 48)
        color = random.choice([
            (190, 178, 150),
            (205, 192, 165),
            (176, 160, 132),
            (220, 207, 181),
        ])
        alpha = random.randint(10, 22)

        base = draw_soft_stain(base, x, y, rx, ry, color, alpha, blur=random.randint(14, 26))

    bottom_count = random.randint(2, 5)

    for _ in range(bottom_count):
        x = random.randint(80, width - 80)
        y = random.randint(1010, height - 60)
        rx = random.randint(25, 90)
        ry = random.randint(10, 45)

        color = random.choice([
            (196, 184, 155),
            (212, 198, 170),
            (180, 164, 138),
        ])
        alpha = random.randint(8, 18)

        base = draw_soft_stain(base, x, y, rx, ry, color, alpha, blur=random.randint(18, 32))

    return base


def make_old_paper_frame(width, height):
    base = Image.new("RGB", (width, height), "#f3eddf")

    warm = Image.new("RGB", (width, height), (255, 239, 210))
    base = Image.blend(base, warm, 0.25)

    noise = Image.effect_noise((width, height), 24).convert("RGB")
    base = Image.blend(base, noise, 0.04)

    edge = Image.new("L", (width, height), 0)
    px = edge.load()

    for y in range(height):
        for x in range(width):
            d = min(x, width - x, y, height - y)
            v = max(0, 1 - d / 240)
            px[x, y] = int(255 * (v ** 1.8) * 0.20)

    aged = Image.new("RGB", (width, height), (216, 204, 182))
    base = Image.composite(aged, base, edge)

    gradient = Image.new("L", (1, height))
    for y in range(height):
        gradient.putpixel((0, y), int(255 * (y / height) ** 2 * 0.11))

    alpha = gradient.resize((width, height))
    shade = Image.new("RGB", (width, height), (223, 214, 196))
    base = Image.composite(shade, base, alpha)

    base = add_edge_and_bottom_stains(base, width, height)

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

    photo_x = 50 + random.randint(-5, 5)
    photo_y = 80 + random.randint(-4, 4)
    frame.paste(img, (photo_x, photo_y), img)

    draw = ImageDraw.Draw(frame)

    text = user_texts.get(user_id, "")
    date = user_dates.get(user_id, "")

    font = fit_text(draw, text, 820)
    date_font = load_font(40)

    bbox = draw.textbbox((0, 0), text, font=font)
    text_x = (1000 - (bbox[2] - bbox[0])) // 2 + random.randint(-15, 15)

    draw_hand_text(frame, text, text_x, 1030 + random.randint(-4, 6), font)

    if date:
        bbox = draw.textbbox((0, 0), date, font=date_font)
        date_x = (1000 - (bbox[2] - bbox[0])) // 2 + random.randint(-10, 10)
        draw.text((date_x, 1133 + random.randint(-2, 5)), date, fill=(125, 125, 118), font=date_font)

    final_noise = Image.effect_noise(frame.size, 10).convert("RGB")
    frame = Image.blend(frame, final_noise, 0.014)

    frame.save(f"/tmp/output_{key}.jpg", quality=95)
    return key


def date_quick_reply():
    today = (datetime.utcnow() + timedelta(hours=9)).strftime("%Y.%m.%d")
    return QuickReply(items=[
        QuickReplyButton(action=MessageAction(label="今日", text=today)),
        QuickReplyButton(action=MessageAction(label="なし", text="なし")),
    ])


def after_generate_quick_reply():
    return QuickReply(items=[
        QuickReplyButton(action=MessageAction(label="もう一回つくる", text="やり直し")),
        QuickReplyButton(action=MessageAction(label="文字だけ変える", text="文字変更")),
        QuickReplyButton(action=MessageAction(label="日付だけ変える", text="日付変更")),
    ])


@app.route("/")
def home():
    return "OK"


@app.route("/output/<key>.jpg")
def output(key):
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

    content = line_bot_api.get_message_content(event.message.id)

    with open(f"/tmp/input_{key}.jpg", "wb") as f:
        for chunk in content.iter_content():
            f.write(chunk)

    user_states[user_id] = "text"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text="画像受け取ったで📸\n下に入れる文字を送って！")
    )


@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    user_id = event.source.user_id
    msg = event.message.text.strip()

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
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="日付を送ってね📅 手入力でもOK。不要なら「なし」", quick_reply=date_quick_reply())
        )
        return

    if user_states.get(user_id) == "text":
        if len(msg) > MAX_TEXT_LENGTH:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"文字は{MAX_TEXT_LENGTH}文字までにして🙏")
            )
            return

        user_texts[user_id] = msg
        user_states[user_id] = "date"

        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="日付を送ってね📅 手入力でもOK。不要なら「なし」", quick_reply=date_quick_reply())
        )
        return

    if user_states.get(user_id) == "date":
        user_dates[user_id] = "" if msg in ["なし", "無し", "不要", "いらない"] else msg

        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="いい感じに現像中…📸")
        )

        key = make_cheki(user_id)
        image_url = f"{BASE_URL}/output/{key}.jpg?{int(time.time())}"

        line_bot_api.push_message(
            user_id,
            ImageSendMessage(
                original_content_url=image_url,
                preview_image_url=image_url
            )
        )

        line_bot_api.push_message(
            user_id,
            TextSendMessage(text="完成したで📸 もう一回つくる？", quick_reply=after_generate_quick_reply())
        )

        user_states[user_id] = None
        return

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text="まず画像を送ってね📸")
    )
