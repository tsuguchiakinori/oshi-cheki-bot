import os
import time
import hashlib
import json
import uuid
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

import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__)

CHANNEL_ACCESS_TOKEN = os.environ["CHANNEL_ACCESS_TOKEN"]
CHANNEL_SECRET = os.environ["CHANNEL_SECRET"]
BASE_URL = "https://oshi-cheki-bot.onrender.com"

SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID")
GOOGLE_CREDENTIALS = os.environ.get("GOOGLE_CREDENTIALS")

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

user_states = {}
user_texts = {}
user_dates = {}
user_filters = {}
user_sessions = {}
user_image_info = {}
user_retry_types = {}
user_retry_counts = {}
user_session_generation_counts = {}

MAX_TEXT_LENGTH = 14

SESSION_SHEET_NAME = "user_sessions"

SESSION_HEADERS = [
    "user_id",
    "state",
    "input_text",
    "date_text",
    "filter_type",
    "session_id",
    "image_width",
    "image_height",
    "retry_type",
    "retry_count",
    "session_generation_count",
    "updated_at",
]


def now_jst():
    return datetime.utcnow() + timedelta(hours=9)


def user_key(user_id):
    return hashlib.md5(user_id.encode()).hexdigest()


def get_spreadsheet():
    if not SPREADSHEET_ID or not GOOGLE_CREDENTIALS:
        return None

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    credentials_info = json.loads(GOOGLE_CREDENTIALS)
    credentials = Credentials.from_service_account_info(credentials_info, scopes=scopes)
    client = gspread.authorize(credentials)
    return client.open_by_key(SPREADSHEET_ID)


def get_sheet():
    spreadsheet = get_spreadsheet()
    if spreadsheet is None:
        return None
    return spreadsheet.sheet1


def get_session_sheet():
    spreadsheet = get_spreadsheet()
    if spreadsheet is None:
        return None

    try:
        worksheet = spreadsheet.worksheet(SESSION_SHEET_NAME)
    except Exception:
        worksheet = spreadsheet.add_worksheet(
            title=SESSION_SHEET_NAME,
            rows=1000,
            cols=len(SESSION_HEADERS),
        )
        worksheet.append_row(SESSION_HEADERS)
        return worksheet

    values = worksheet.get_all_values()

    if not values:
        worksheet.append_row(SESSION_HEADERS)
    elif values[0] != SESSION_HEADERS:
        worksheet.clear()
        worksheet.append_row(SESSION_HEADERS)

    return worksheet


def save_user_session_state(user_id):
    try:
        sheet = get_session_sheet()
        if sheet is None:
            return

        row_values = [
            user_id,
            user_states.get(user_id, "") or "",
            user_texts.get(user_id, ""),
            user_dates.get(user_id, ""),
            user_filters.get(user_id, "good"),
            user_sessions.get(user_id, ""),
            user_image_info.get(user_id, {}).get("width", ""),
            user_image_info.get(user_id, {}).get("height", ""),
            user_retry_types.get(user_id, "initial"),
            user_retry_counts.get(user_id, 0),
            user_session_generation_counts.get(user_id, 0),
            now_jst().strftime("%Y-%m-%d %H:%M:%S"),
        ]

        records = sheet.get_all_records()
        target_row = None

        for i, record in enumerate(records, start=2):
            if str(record.get("user_id", "")) == user_id:
                target_row = i
                break

        if target_row:
            sheet.update(f"A{target_row}:L{target_row}", [row_values])
        else:
            sheet.append_row(row_values, value_input_option="USER_ENTERED")

    except Exception as e:
        print("save_user_session_state error:", e)


def load_user_session_state(user_id):
    try:
        sheet = get_session_sheet()
        if sheet is None:
            return False

        records = sheet.get_all_records()

        for record in records:
            if str(record.get("user_id", "")) == user_id:
                user_states[user_id] = record.get("state", "") or None
                user_texts[user_id] = record.get("input_text", "")
                user_dates[user_id] = record.get("date_text", "")
                user_filters[user_id] = record.get("filter_type", "good")
                user_sessions[user_id] = record.get("session_id", "")

                user_image_info[user_id] = {
                    "width": record.get("image_width", ""),
                    "height": record.get("image_height", ""),
                }

                user_retry_types[user_id] = record.get("retry_type", "initial")

                try:
                    user_retry_counts[user_id] = int(record.get("retry_count", 0) or 0)
                except Exception:
                    user_retry_counts[user_id] = 0

                try:
                    user_session_generation_counts[user_id] = int(
                        record.get("session_generation_count", 0) or 0
                    )
                except Exception:
                    user_session_generation_counts[user_id] = 0

                return True

        return False

    except Exception as e:
        print("load_user_session_state error:", e)
        return False


def get_existing_user_stats(sheet, user_id):
    try:
        records = sheet.get_all_records()
        user_records = [r for r in records if str(r.get("user_id", "")) == user_id]

        if not user_records:
            return {
                "previous_count": 0,
                "first_created_at": "",
                "last_created_at": "",
            }

        created_list = [
            r.get("created_at", "")
            for r in user_records
            if r.get("created_at", "")
        ]

        return {
            "previous_count": len(user_records),
            "first_created_at": created_list[0] if created_list else "",
            "last_created_at": created_list[-1] if created_list else "",
        }

    except Exception as e:
        print("get_existing_user_stats error:", e)
        return {
            "previous_count": 0,
            "first_created_at": "",
            "last_created_at": "",
        }


def get_display_name(user_id):
    try:
        profile = line_bot_api.get_profile(user_id)
        return profile.display_name
    except Exception:
        return ""


def get_filter_label(filter_type):
    if filter_type == "emo":
        return "エモい"
    if filter_type == "bright":
        return "盛れる"
    return "いい感じ"


def get_aspect_ratio_label(width, height):
    if not width or not height:
        return ""

    try:
        width = int(width)
        height = int(height)
    except Exception:
        return ""

    if width == 0 or height == 0:
        return ""

    ratio = width / height

    if abs(ratio - 1.0) < 0.05:
        return "1:1"
    if abs(ratio - 0.8) < 0.05:
        return "4:5"
    if abs(ratio - 0.75) < 0.05:
        return "3:4"
    if abs(ratio - 1.333) < 0.05:
        return "4:3"
    if abs(ratio - 1.777) < 0.08:
        return "16:9"

    return f"{width}:{height}"


def log_generation(user_id, processing_time_sec, output_urls):
    try:
        sheet = get_sheet()

        if sheet is None:
            print("Google Sheets logging skipped")
            return

        created_at = now_jst().strftime("%Y-%m-%d %H:%M:%S")
        stats = get_existing_user_stats(sheet, user_id)

        previous_count = stats["previous_count"]
        first_visit = "TRUE" if previous_count == 0 else "FALSE"
        user_total_generations = previous_count + 1

        first_created_at = stats["first_created_at"] if stats["first_created_at"] else created_at
        last_created_at = created_at

        image_info = user_image_info.get(user_id, {})
        width = image_info.get("width", "")
        height = image_info.get("height", "")

        text = user_texts.get(user_id, "")
        date_text = user_dates.get(user_id, "")
        filter_type = user_filters.get(user_id, "good")
        session_id = user_sessions.get(user_id, "")

        user_session_generation_counts[user_id] = (
            user_session_generation_counts.get(user_id, 0) + 1
        )
        generation_count = user_session_generation_counts.get(user_id, 1)

        retry_count = user_retry_counts.get(user_id, 0)
        retry_type = user_retry_types.get(user_id, "initial")

        row = [
            created_at,
            user_id,
            get_display_name(user_id),
            first_visit,
            user_total_generations,
            session_id,
            get_filter_label(filter_type),
            text,
            len(text),
            "TRUE" if date_text else "FALSE",
            date_text,
            generation_count,
            retry_count,
            retry_type,
            width,
            height,
            get_aspect_ratio_label(width, height),
            round(processing_time_sec, 2),
            "",
            ",".join(output_urls),
            first_created_at,
            last_created_at,
        ]

        sheet.append_row(row, value_input_option="USER_ENTERED")
        print("Logged generation:", row)

    except Exception as e:
        print("Google Sheets logging error:", e)


def load_font(size):
    try:
        return ImageFont.truetype("makiirclehand.ttf", size)
    except Exception:
        return ImageFont.load_default()


def split_text(text):
    if len(text) <= 10:
        return [text]

    mid = len(text) // 2
    return [text[:mid], text[mid:]]


def fit_text(draw, text, max_width, start_size=78, min_size=36):
    size = start_size

    while size >= min_size:
        font = load_font(size)
        bbox = draw.textbbox((0, 0), text, font=font)

        if (bbox[2] - bbox[0]) <= max_width:
            return font

        size -= 2

    return load_font(min_size)


def get_text_width(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def add_light_vignette(img, alpha=28):
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    w, h = img.size

    d.rectangle((0, 0, w, 55), fill=(40, 30, 20, alpha))
    d.rectangle((0, h - 55, w, h), fill=(40, 30, 20, alpha))
    d.rectangle((0, 0, 55, h), fill=(40, 30, 20, alpha))
    d.rectangle((w - 55, 0, w, h), fill=(40, 30, 20, alpha))

    overlay = overlay.filter(ImageFilter.GaussianBlur(42))
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def apply_photo_filter(img, filter_type, variant=0):
    if filter_type == "emo":
        if variant == 0:
            img = ImageEnhance.Color(img).enhance(0.68)
            img = ImageEnhance.Contrast(img).enhance(1.10)
            img = ImageEnhance.Brightness(img).enhance(0.96)

            warm = Image.new("RGB", img.size, (255, 224, 188))
            img = Image.blend(img, warm, 0.22)

            sepia = Image.new("RGB", img.size, (125, 85, 52))
            img = Image.blend(img, sepia, 0.04)

            noise = Image.effect_noise(img.size, 12).convert("RGB")
            img = Image.blend(img, noise, 0.035)

            img = add_light_vignette(img, alpha=30)
            img = img.filter(ImageFilter.GaussianBlur(0.08))

        else:
            img = ImageEnhance.Color(img).enhance(0.58)
            img = ImageEnhance.Contrast(img).enhance(1.16)
            img = ImageEnhance.Brightness(img).enhance(0.88)

            warm = Image.new("RGB", img.size, (245, 214, 178))
            img = Image.blend(img, warm, 0.26)

            sepia = Image.new("RGB", img.size, (105, 70, 45))
            img = Image.blend(img, sepia, 0.07)

            noise = Image.effect_noise(img.size, 16).convert("RGB")
            img = Image.blend(img, noise, 0.052)

            img = add_light_vignette(img, alpha=44)
            img = img.filter(ImageFilter.GaussianBlur(0.12))

    elif filter_type == "bright":
        if variant == 0:
            img = ImageEnhance.Color(img).enhance(1.08)
            img = ImageEnhance.Contrast(img).enhance(1.14)
            img = ImageEnhance.Brightness(img).enhance(1.16)

            cool = Image.new("RGB", img.size, (236, 244, 255))
            img = Image.blend(img, cool, 0.05)

            noise = Image.effect_noise(img.size, 5).convert("RGB")
            img = Image.blend(img, noise, 0.01)

            img = add_light_vignette(img, alpha=12)

        else:
            img = ImageEnhance.Color(img).enhance(0.95)
            img = ImageEnhance.Contrast(img).enhance(1.07)
            img = ImageEnhance.Brightness(img).enhance(1.24)

            white = Image.new("RGB", img.size, (255, 250, 240))
            img = Image.blend(img, white, 0.13)

            cool = Image.new("RGB", img.size, (238, 246, 255))
            img = Image.blend(img, cool, 0.08)

            noise = Image.effect_noise(img.size, 4).convert("RGB")
            img = Image.blend(img, noise, 0.008)

            img = add_light_vignette(img, alpha=8)

    else:
        if variant == 0:
            img = ImageEnhance.Color(img).enhance(0.82)
            img = ImageEnhance.Contrast(img).enhance(1.07)
            img = ImageEnhance.Brightness(img).enhance(1.03)

            warm = Image.new("RGB", img.size, (255, 234, 202))
            img = Image.blend(img, warm, 0.11)

            sepia = Image.new("RGB", img.size, (120, 82, 50))
            img = Image.blend(img, sepia, 0.018)

            noise = Image.effect_noise(img.size, 7).convert("RGB")
            img = Image.blend(img, noise, 0.022)

            img = add_light_vignette(img, alpha=20)
            img = img.filter(ImageFilter.GaussianBlur(0.05))

        else:
            img = ImageEnhance.Color(img).enhance(0.72)
            img = ImageEnhance.Contrast(img).enhance(0.96)
            img = ImageEnhance.Brightness(img).enhance(1.09)

            cream = Image.new("RGB", img.size, (255, 242, 218))
            img = Image.blend(img, cream, 0.17)

            noise = Image.effect_noise(img.size, 8).convert("RGB")
            img = Image.blend(img, noise, 0.025)

            img = add_light_vignette(img, alpha=16)
            img = img.filter(ImageFilter.GaussianBlur(0.07))

    return img


def make_old_paper_frame(width, height):
    base = Image.new("RGB", (width, height), "#f3eddf")

    warm = Image.new("RGB", (width, height), (255, 239, 210))
    base = Image.blend(base, warm, 0.23)

    noise = Image.effect_noise((width, height), 12).convert("RGB")
    base = Image.blend(base, noise, 0.025)

    return base


def round_corners(img, radius=18):
    img = img.convert("RGBA")
    mask = Image.new("L", img.size, 0)
    draw = ImageDraw.Draw(mask)

    draw.rounded_rectangle(
        (0, 0, img.size[0], img.size[1]),
        radius,
        fill=255
    )

    img.putalpha(mask)
    return img


def make_cheki(user_id, variant=0):
    key = user_key(user_id)
    input_path = f"/tmp/input_{key}.jpg"

    if not os.path.exists(input_path):
        raise FileNotFoundError("input image not found")

    filter_type = user_filters.get(user_id, "good")

    img = Image.open(input_path).convert("RGB")

    w, h = img.size
    size = min(w, h)

    img = img.crop((
        (w - size) // 2,
        (h - size) // 2,
        (w + size) // 2,
        (h + size) // 2
    ))

    img = img.resize((900, 900))
    img = apply_photo_filter(img, filter_type, variant=variant)
    img = round_corners(img, radius=18)

    frame = make_old_paper_frame(1000, 1300)
    frame.paste(img, (50, 80), img)

    draw = ImageDraw.Draw(frame)

    text = user_texts.get(user_id, "")
    date_text = user_dates.get(user_id, "")

    lines = split_text(text) if text else [""]
    longest_line = max(lines, key=len) if lines else ""

    title_font = fit_text(
        draw,
        longest_line,
        max_width=760,
        start_size=78,
        min_size=36
    )

    line_height = 72

    if len(lines) == 1:
        start_y = 1040
    else:
        start_y = 1010

    for i, line in enumerate(lines):
        text_width = get_text_width(draw, line, title_font)

        draw.text(
            ((1000 - text_width) / 2, start_y + i * line_height),
            line,
            font=title_font,
            fill=(35, 28, 24),
        )

    if date_text:
        date_font = load_font(42)
        date_width = get_text_width(draw, date_text, date_font)

        if len(lines) == 1:
            date_y = 1140
        else:
            date_y = 1200

        draw.text(
            ((1000 - date_width) / 2, date_y),
            date_text,
            font=date_font,
            fill=(120, 110, 100),
        )

    output_key = f"{key}_{variant}"
    frame.save(f"/tmp/output_{output_key}.jpg", quality=92)

    return output_key


def date_quick_reply():
    today = now_jst().strftime("%Y.%m.%d")

    return QuickReply(items=[
        QuickReplyButton(action=MessageAction(label="今日", text=today)),
        QuickReplyButton(action=MessageAction(label="なし", text="なし")),
    ])


def filter_quick_reply():
    return QuickReply(items=[
        QuickReplyButton(action=MessageAction(label="いい感じ", text="いい感じ")),
        QuickReplyButton(action=MessageAction(label="エモい", text="エモい")),
        QuickReplyButton(action=MessageAction(label="盛れる", text="盛れる")),
    ])


def after_generate_quick_reply():
    return QuickReply(items=[
        QuickReplyButton(action=MessageAction(label="もう一回つくる", text="やり直し")),
        QuickReplyButton(action=MessageAction(label="雰囲気だけ変える", text="雰囲気だけ変える")),
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


def generate_and_send(user_id):
    start_time = time.time()

    try:
        output_keys = []
        output_urls = []

        for i in range(2):
            output_key = make_cheki(user_id, variant=i)
            output_keys.append(output_key)

        line_bot_api.push_message(
            user_id,
            TextSendMessage(
                text="2パターン作ったよ📸\n好きな方を保存してね👇"
            )
        )

        for output_key in output_keys:
            image_url = f"{BASE_URL}/output/{output_key}.jpg?{int(time.time())}"
            output_urls.append(image_url)

            line_bot_api.push_message(
                user_id,
                ImageSendMessage(
                    original_content_url=image_url,
                    preview_image_url=image_url
                )
            )

        line_bot_api.push_message(
            user_id,
            TextSendMessage(
                text="いい感じにできたね📸✨\nSNSでシェアしてみて👇\n#推しフィルム\n\nもう一回つくる？",
                quick_reply=after_generate_quick_reply()
            )
        )

        processing_time_sec = time.time() - start_time
        log_generation(user_id, processing_time_sec, output_urls)

        user_states[user_id] = None
        save_user_session_state(user_id)

    except FileNotFoundError:
        user_states[user_id] = None
        save_user_session_state(user_id)

        line_bot_api.push_message(
            user_id,
            TextSendMessage(
                text="時間が経って画像データが消えちゃったみたい🙏\nもう一度画像を送ってね📸"
            )
        )

    except Exception as e:
        print("generate_and_send error:", e)

        line_bot_api.push_message(
            user_id,
            TextSendMessage(
                text="ごめん、うまく作れなかったみたい🙏\nもう一度画像を送って試してみて📸"
            )
        )


@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    user_id = event.source.user_id
    key = user_key(user_id)

    try:
        content = line_bot_api.get_message_content(event.message.id)

        with open(f"/tmp/input_{key}.jpg", "wb") as f:
            for chunk in content.iter_content():
                f.write(chunk)

        try:
            img = Image.open(f"/tmp/input_{key}.jpg")

            user_image_info[user_id] = {
                "width": img.size[0],
                "height": img.size[1],
            }

        except Exception:
            user_image_info[user_id] = {
                "width": "",
                "height": "",
            }

        user_sessions[user_id] = str(uuid.uuid4())
        user_texts[user_id] = ""
        user_dates[user_id] = ""
        user_filters[user_id] = "good"
        user_retry_types[user_id] = "initial"
        user_retry_counts[user_id] = 0
        user_session_generation_counts[user_id] = 0
        user_states[user_id] = "filter"

        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(
                text="どの雰囲気にする？👇",
                quick_reply=filter_quick_reply()
            )
        )

        save_user_session_state(user_id)

    except Exception as e:
        print("handle_image error:", e)

        try:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(
                    text="画像の受け取りに失敗しちゃったみたい🙏\nもう一度画像を送ってね📸"
                )
            )
        except Exception as reply_error:
            print("handle_image reply error:", reply_error)


@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    user_id = event.source.user_id
    msg = event.message.text.strip()

    load_user_session_state(user_id)

    if msg == "やり直し":
        user_states[user_id] = None
        user_filters[user_id] = "good"
        user_texts[user_id] = ""
        user_dates[user_id] = ""

        user_retry_types[user_id] = "やり直し"
        user_retry_counts[user_id] = user_retry_counts.get(user_id, 0) + 1

        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="もう一度画像を送ってね📸")
        )

        save_user_session_state(user_id)
        return

    if msg == "雰囲気だけ変える":
        user_states[user_id] = "filter_change"
        user_retry_types[user_id] = "雰囲気変更"
        user_retry_counts[user_id] = user_retry_counts.get(user_id, 0) + 1

        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(
                text="どの雰囲気に変える？👇",
                quick_reply=filter_quick_reply()
            )
        )

        save_user_session_state(user_id)
        return

    if msg == "文字変更":
        user_states[user_id] = "text"
        user_retry_types[user_id] = "文字変更"
        user_retry_counts[user_id] = user_retry_counts.get(user_id, 0) + 1

        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="新しい文字を送って！")
        )

        save_user_session_state(user_id)
        return

    if msg == "日付変更":
        user_states[user_id] = "date"
        user_retry_types[user_id] = "日付変更"
        user_retry_counts[user_id] = user_retry_counts.get(user_id, 0) + 1

        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(
                text="日付を送ってね📅 手入力でもOK。不要なら「なし」",
                quick_reply=date_quick_reply()
            )
        )

        save_user_session_state(user_id)
        return

    if user_states.get(user_id) in ["filter", "filter_change"]:

        filter_map = {
            "いい感じ": "good",
            "エモい": "emo",
            "盛れる": "bright",
        }

        if msg in filter_map:
            user_filters[user_id] = filter_map[msg]

            if user_states.get(user_id) == "filter_change":
                user_states[user_id] = None

                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(
                        text=f"「{msg}」で作り直すね📸"
                    )
                )

                save_user_session_state(user_id)
                generate_and_send(user_id)
                return

            user_states[user_id] = "text"

            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(
                    text=f"「{msg}」で作るね📸\n下に入れる文字を送って！"
                )
            )

            save_user_session_state(user_id)
            return

        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(
                text="ボタンから雰囲気を選んでね👇",
                quick_reply=filter_quick_reply()
            )
        )

        return

    if user_states.get(user_id) == "text":

        if len(msg) > MAX_TEXT_LENGTH:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(
                    text=f"文字は{MAX_TEXT_LENGTH}文字までにして🙏"
                )
            )

            return

        user_texts[user_id] = msg
        user_states[user_id] = "date"

        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(
                text="日付を送ってね📅 手入力でもOK。不要なら「なし」",
                quick_reply=date_quick_reply()
            )
        )

        save_user_session_state(user_id)
        return

    if user_states.get(user_id) == "date":

        user_dates[user_id] = (
            ""
            if msg in ["なし", "無し", "不要", "いらない"]
            else msg
        )

        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="2パターン現像中…📸")
        )

        save_user_session_state(user_id)
        generate_and_send(user_id)
        return

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text="まず画像を送ってね📸")
    )
