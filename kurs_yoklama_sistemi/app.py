import os
import csv
import io
import shutil
import socket
from datetime import datetime, timedelta
from flask import (
    Flask, render_template, request, redirect, url_for, 
    session, flash, Response, jsonify, send_from_directory
)
import database as db

app = Flask(__name__)
app.secret_key = "kurs-yoklama-gizli-anahtari-2026"

# Doğrudan Resmi Jujutsu Kaisen Anime Sahneleri (1080p Orijinal Kareler)
OFFICIAL_ANIME_URLS = {
    "sukuna": "https://wallpapercave.com/wp/wp8597375.jpg",
    "gojo": "https://wallpaperaccess.com/full/9051452.jpg",
    "itadori": "https://wallpaperaccess.com/full/8060839.jpg",
    "toji": "https://wallpaperaccess.com/full/6352979.jpg",
    "yuta": "https://wallpaperaccess.com/full/7633281.jpg",
    "mahoraga": "https://wallpaperaccess.com/full/10499015.jpg",
}

THEMES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "img", "themes")

def get_official_anime_frame(theme_name):
    try:
        os.makedirs(THEMES_DIR, exist_ok=True)
        target_file = os.path.join(THEMES_DIR, f"{theme_name}.jpg")
        
        if os.path.exists(target_file) and os.path.getsize(target_file) > 20000:
            return target_file
            
        url = OFFICIAL_ANIME_URLS.get(theme_name)
        if not url:
            return None
            
        import urllib.request
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=6) as resp:
            if resp.status == 200:
                data = resp.read()
                if len(data) > 15000:
                    with open(target_file, "wb") as f:
                        f.write(data)
                    return target_file
    except Exception:
        pass
    return None

@app.route("/static/img/themes/<theme_name>.jpg")
def serve_theme_bg(theme_name):
    theme_name = theme_name.lower().strip()
    if theme_name not in OFFICIAL_ANIME_URLS:
        theme_name = "sukuna"
        
    local_path = get_official_anime_frame(theme_name)
    if local_path and os.path.exists(local_path):
        return send_from_directory(THEMES_DIR, f"{theme_name}.jpg")
        
    return redirect(OFFICIAL_ANIME_URLS[theme_name])

@app.route("/static/img/sukuna_fuga.jpg")
def serve_sukuna_bg():
    return serve_theme_bg("sukuna")

# Veritabanını başlat
db.init_db()

# Türkçe Ay ve Gün İsimleri
TR_MONTHS = [
    "", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"
]
TR_DAYS = [
    "Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"
]

def format_date_tr(date_str):
    """YYYY-MM-DD formatındaki tarihi '30 Ağustos 2026 Pazar' haline getirir."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        day = dt.day
        month = TR_MONTHS[dt.month]
        year = dt.year
        weekday = TR_DAYS[dt.weekday()]
        return f"{day} {month} {year} {weekday}"
    except Exception:
        return date_str

def get_default_date():
    """
    Varsayılan olarak bugünün tarihini döner.
    """
    return datetime.now().strftime("%Y-%m-%d")

def get_local_ip():
    """Aynı Wi-Fi ağındaki diğer cihazların (öğrencilerin) erişebilmesi için yerel IP'yi bulur."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

# --- ÖĞRENCİ SAYFALARI ---

@app.route("/")
def index():
    """Öğrencinin 7/24 yoklama ve mazeret bildirebildiği ana sayfa."""
    default_date = get_default_date()
    default_date_display = format_date_tr(default_date)
    registered_students = db.get_all_students()
    announcements = db.get_active_announcements()
    course_name = db.get_setting("course_name", "Kurs Yoklama Sistemi")
    current_user = session.get("user")
    current_student = session.get("student")
    schedules = db.get_all_schedules()
    
    return render_template(
        "index.html",
        default_date=default_date,
        default_date_display=default_date_display,
        registered_students=registered_students,
        announcements=announcements,
        course_name=course_name,
        current_user=current_user,
        current_student=current_student,
        schedules=schedules
    )

@app.route("/announcements/quick-add", methods=["POST"])
def quick_add_announcement():
    """Öğretmenlerin doğrudan ana sayfadan duyuru ekleyebilmesini sağlar."""
    user = session.get("user")
    if not user:
        flash("Duyuru yayınlayabilmek için öğretmen veya yönetici hesabı ile giriş yapmalısınız.", "warning")
        return redirect(url_for("login"))
        
    title = request.form.get("title", "").strip()
    content = request.form.get("content", "").strip()
    badge = request.form.get("badge", "Duyuru").strip()
    
    if title and content:
        db.add_announcement(title, content, badge)
        flash(f"📢 '{title}' başlıklı duyuru tüm öğrencilere yayınlandı.", "success")
    else:
        flash("Lütfen duyuru başlığını ve açıklamasını eksiksiz giriniz.", "danger")
        
    return redirect(url_for("index"))

@app.route("/submit", methods=["POST"])
def submit():
    """Öğrenci bildirim formu gönderimi."""
    student_name = request.form.get("student_name", "").strip()
    custom_name = request.form.get("custom_name", "").strip()
    
    # Eğer açılır listeden 'Diğer / Listede Yokum' seçilmişse veya doğrudan isim yazılmışsa
    if student_name == "DIGER" or not student_name:
        student_name = custom_name

    student_no = request.form.get("student_no", "").strip()
    target_date = request.form.get("target_date", "").strip()
    status = request.form.get("status", "").strip()
    excuse = request.form.get("excuse", "").strip()
    phone = request.form.get("phone", "").strip()

    if not student_name:
        flash("Lütfen adınızı ve soyadınızı giriniz.", "danger")
        return redirect(url_for("index"))

    # Eğer bu isim kayıtlı öğrencilerle eşleşiyorsa (büyük/küçük, bitişik/ayrık toleranslı), resmi adı ve nosunu al
    matched_student = db.get_student_by_name(student_name)
    if matched_student:
        student_name = matched_student["name"]
        if not student_no and matched_student.get("student_no"):
            student_no = matched_student["student_no"]
        if not phone and matched_student.get("phone"):
            phone = matched_student["phone"]

    if not target_date:
        target_date = get_default_date()

    if status not in ["geliyorum", "gelemiyorum", "gec_kalacagim"]:
        flash("Lütfen katılım durumunuzu seçiniz.", "danger")
        return redirect(url_for("index"))

    # Veritabanına kaydet veya güncelle
    db.save_or_update_attendance(
        student_name=student_name,
        student_no=student_no,
        target_date=target_date,
        status=status,
        excuse=excuse,
        phone=phone
    )

    status_labels = {
        "geliyorum": ("Geliyorum", "green"),
        "gelemiyorum": ("Gelemeyeceğim", "red"),
        "gec_kalacagim": ("Geç Kalacağım", "yellow")
    }
    status_text, status_color = status_labels.get(status, ("Bildirildi", "blue"))

    return render_template(
        "success.html",
        student_name=student_name,
        target_date_display=format_date_tr(target_date),
        status_text=status_text,
        status_color=status_color,
        excuse=excuse
    )

# --- YENİ KULLANICI / ÖĞRENCİ / ÖĞRETMEN KAYDI ---

@app.route("/register", methods=["GET", "POST"])
def register():
    course_name = db.get_setting("course_name", "Kurs Yoklama Sistemi")
    
    if request.method == "POST":
        reg_type = request.form.get("reg_type", "student")
        
        if reg_type == "student":
            name = request.form.get("name", "").strip()
            student_no = request.form.get("student_no", "").strip()
            phone = request.form.get("phone", "").strip()
            password = request.form.get("password", "123456").strip() or "123456"
            
            if not name:
                flash("Lütfen adınızı ve soyadınızı giriniz.", "danger")
                return redirect(url_for("register", type="student"))
                
            if db.add_student(name, student_no, phone, password):
                student = db.get_student_by_name(name)
                session["student"] = student
                session.pop("user", None)
                session.pop("is_admin", None)
                flash(f"🎉 Kaydınız tamamlandı ve giriş yapıldı! Hoş geldin, {name}.", "success")
                return redirect(url_for("index"))
            else:
                flash(f"'{name}' isimli öğrenci zaten kayıtlı! Öğrenci girişi yaparak devam edebilirsiniz.", "warning")
                return redirect(url_for("login", type="student"))
                
        elif reg_type == "teacher":
            full_name = request.form.get("full_name", "").strip()
            subject = request.form.get("subject", "Genel").strip()
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "").strip()
            
            if not full_name or not username or not password:
                flash("Lütfen tüm zorunlu alanları doldurunuz.", "danger")
                return redirect(url_for("register", type="teacher"))
                
            if db.add_teacher(username, password, full_name, subject, role="teacher"):
                flash(f"🎉 Öğretmen hesabınız başarıyla oluşturuldu! Şimdi giriş yapabilirsiniz.", "success")
                return redirect(url_for("login", type="teacher"))
            else:
                flash(f"'{username}' kullanıcı adı zaten kullanılıyor! Lütfen farklı bir kullanıcı adı seçiniz.", "danger")
                return redirect(url_for("register", type="teacher"))

        elif reg_type == "admin":
            full_name = request.form.get("full_name", "").strip()
            subject = request.form.get("subject", "Boş İşler Müdürü").strip() or "Boş İşler Müdürü"
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "").strip()
            
            if not full_name or not username or not password:
                flash("Lütfen tüm zorunlu alanları doldurunuz.", "danger")
                return redirect(url_for("register", type="admin"))
                
            if db.add_teacher(username, password, full_name, subject, role="admin"):
                client_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
                db.log_login_attempt(
                    username=username,
                    full_name=full_name,
                    role="Yönetici (Yeni Kayıt)",
                    ip_address=client_ip,
                    status="Admin Hesabı Oluşturuldu"
                )
                flash(f"👑 '{full_name}' isimli Yönetici / Admin hesabınız ({username}) başarıyla oluşturuldu! Şimdi giriş yapabilirsiniz.", "success")
                return redirect(url_for("login", type="teacher"))
            else:
                flash(f"'{username}' kullanıcı adı zaten kullanılıyor! Lütfen farklı bir kullanıcı adı seçiniz.", "danger")
                return redirect(url_for("register", type="admin"))
                
    return render_template("register.html", course_name=course_name)

@app.route("/admin-kayit")
@app.route("/admin/kayit")
@app.route("/admin/register")
def admin_register_shortcut():
    """Doğrudan admin kayıt sekmesine yönlendirir."""
    return redirect(url_for("register", type="admin"))

# --- ÖĞRENCİ / ÖĞRETMEN / YÖNETİCİ GİRİŞ & ÇIKIŞ ---

@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user"):
        return redirect(url_for("admin_dashboard"))
    if session.get("student"):
        return redirect(url_for("index"))

    course_name = db.get_setting("course_name", "Kurs Yoklama Sistemi")

    if request.method == "POST":
        login_type = request.form.get("login_type", "teacher")
        identifier = request.form.get("username", "").strip()
        student_id_input = request.form.get("student_identifier", "").strip()
        password = request.form.get("password", "").strip()
        client_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
        admin_pass = db.get_setting("admin_password", "admin123")

        # Arama anahtarı (öğrenci no, ad soyad veya kullanıcı adı)
        search_key = student_id_input if student_id_input else identifier

        # 1. ÖĞRENCİ GİRİŞİ KONTROLÜ
        student = db.authenticate_student(search_key, password)

        # 2. ÖĞRETMEN / YÖNETİCİ GİRİŞİ KONTROLÜ
        teacher = db.authenticate_teacher(search_key, password)

        # 3. YÖNETİCİ ŞİFRESİ İLE HIZLI GİRİŞ (Esnek şifre & kullanıcı adı eşleşmesi)
        if not teacher and db.passwords_match(password, admin_pass):
            if not search_key or db.identifiers_match(search_key, "admin") or db.identifiers_match(search_key, "Boş İşler Müdürü") or db.identifiers_match(search_key, "yonetici"):
                teacher = {"id": 1, "username": "admin", "full_name": "Boş İşler Müdürü", "role": "admin", "subject": "Yönetim"}

        # ÖNCELİKLENDİRME:
        # Eğer form tipi student ise ve student bulunduysa -> Öğrenci Girişi
        # Eğer form tipi teacher ise ve teacher bulunduysa -> Öğretmen Girişi
        # Bulunamadıysa çapraz kontrol (öğretmen sekmesindeki öğrenci veya öğrenci sekmesindeki öğretmen)

        if login_type == "student":
            target_user = student or teacher
        else:
            target_user = teacher or student

        if target_user:
            # Öğrenci mi, Öğretmen/Yönetici mi?
            if "student_no" in target_user or target_user.get("role") == "student" or "role" not in target_user:
                # Öğrenci oturumu başlat
                session["student"] = target_user
                session.pop("user", None)
                session.pop("is_admin", None)
                
                db.update_student_last_login(target_user["id"])
                db.log_login_attempt(
                    username=target_user.get("student_no") or target_user["name"],
                    full_name=target_user["name"],
                    role="Öğrenci",
                    ip_address=client_ip,
                    status="Başarılı Öğrenci Girişi"
                )
                
                flash(f"🎉 Hoş geldin, {target_user['name']}! Girişin başarıyla yapıldı.", "success")
                return redirect(url_for("index"))
            else:
                # Öğretmen / Yönetici oturumu başlat
                session["user"] = target_user
                session["is_admin"] = True
                session.pop("student", None)
                
                db.update_last_login(target_user["id"])
                db.log_login_attempt(
                    username=target_user["username"],
                    full_name=target_user["full_name"],
                    role=target_user.get("role", "teacher"),
                    ip_address=client_ip,
                    status="Başarılı Yönetici Girişi"
                )
                
                flash(f"Hoş geldiniz, {target_user['full_name']} ({target_user.get('subject', 'Yönetim')}).", "success")
                return redirect(url_for("admin_dashboard"))

        # Hatalı Giriş
        db.log_login_attempt(
            username=search_key if search_key else "Bilinmeyen",
            full_name="-",
            role="Misafir",
            ip_address=client_ip,
            status="Hatalı Giriş Denemesi"
        )
        flash("Girdiğiniz isim, numara veya şifre eşleşmedi. Lütfen bilgilerinizi kontrol ediniz.", "danger")
        return redirect(url_for("login", type=login_type))

    return render_template("login.html", course_name=course_name)

@app.route("/logout")
def logout():
    session.pop("user", None)
    session.pop("is_admin", None)
    session.pop("student", None)
    flash("Başarıyla çıkış yapıldı.", "info")
    return redirect(url_for("index"))

# --- KAYITLI HESAPLAR, ŞİFRELER VE GİRİŞ LOGLARI YÖNETİMİ ---

@app.route("/admin/hesaplar")
@app.route("/admin/ogretmenler")
def admin_accounts():
    if not session.get("is_admin"):
        return redirect(url_for("login"))

    accounts = db.get_all_accounts()
    students = db.get_all_students()
    login_logs = db.get_login_logs(limit=60)
    current_user = session.get("user", {})
    course_name = db.get_setting("course_name", "Kurs Yoklama Sistemi")

    return render_template(
        "accounts.html",
        accounts=accounts,
        students=students,
        login_logs=login_logs,
        current_user=current_user,
        course_name=course_name
    )

@app.route("/admin/hesaplar/add", methods=["POST"])
@app.route("/admin/ogretmenler/add", methods=["POST"])
def add_account_route():
    if not session.get("is_admin"):
        return redirect(url_for("login"))

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()
    full_name = request.form.get("full_name", "").strip()
    subject = request.form.get("subject", "Genel").strip()
    role = request.form.get("role", "teacher").strip()

    if db.add_teacher(username, password, full_name, subject, role):
        flash(f"🎉 '{full_name}' isimli hesap ({username}) şifresiyle birlikte başarıyla oluşturuldu.", "success")
    else:
        flash(f"❌ '{username}' kullanıcı adı zaten kayıtlı veya eksik bilgi girdiniz!", "danger")

    return redirect(url_for("admin_accounts"))

@app.route("/admin/hesaplar/update", methods=["POST"])
def update_account_route():
    if not session.get("is_admin"):
        return redirect(url_for("login"))

    user_id = request.form.get("user_id")
    full_name = request.form.get("full_name", "").strip()
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()
    subject = request.form.get("subject", "Genel").strip()
    role = request.form.get("role", "teacher").strip()

    if not user_id:
        flash("Geçersiz kullanıcı ID.", "danger")
        return redirect(url_for("admin_accounts"))

    if db.update_account(user_id, full_name, username, password, subject, role):
        flash(f"✅ '{full_name}' kullanıcısının hesap bilgileri ve şifresi güncellendi.", "success")
    else:
        flash("Hesap güncellenirken bir hata oluştu veya kullanıcı adı çakışıyor.", "danger")

    return redirect(url_for("admin_accounts"))

@app.route("/admin/hesaplar/delete/<int:user_id>", methods=["POST"])
@app.route("/admin/ogretmenler/delete/<int:user_id>", methods=["POST"])
def delete_account_route(user_id):
    if not session.get("is_admin"):
        return redirect(url_for("login"))

    if db.delete_account(user_id):
        flash("🗑️ Kullanıcı hesabı sistemden silindi.", "success")
    else:
        flash("❌ Ana yönetici hesabı silinemez!", "danger")

    return redirect(url_for("admin_accounts"))

@app.route("/admin/hesaplar/clear-logs", methods=["POST"])
def clear_logs_route():
    if not session.get("is_admin"):
        return redirect(url_for("login"))

    db.clear_login_logs()
    flash("🧹 Giriş geçmişi kayıtları temizlendi.", "info")
    return redirect(url_for("admin_accounts"))

@app.route("/admin/students/save", methods=["POST"])
def save_student_account_route():
    if not session.get("is_admin"):
        return redirect(url_for("login"))

    student_id = request.form.get("student_id")
    name = request.form.get("name", "").strip()
    student_no = request.form.get("student_no", "").strip()
    phone = request.form.get("phone", "").strip()
    password = request.form.get("password", "123456").strip() or "123456"

    if not name:
        flash("Öğrenci adı zorunludur.", "danger")
        return redirect(url_for("admin_accounts"))

    if student_id:
        if db.update_student(student_id, name, student_no, phone, password):
            flash(f"✅ '{name}' isimli öğrencinin hesap bilgileri ve şifresi güncellendi.", "success")
        else:
            flash("Öğrenci güncellenirken hata oluştu.", "danger")
    else:
        if db.add_student(name, student_no, phone, password):
            flash(f"🎉 '{name}' isimli öğrenci ve şifresi başarıyla kaydedildi.", "success")
        else:
            flash(f"'{name}' isimli öğrenci zaten kayıtlı!", "warning")

    return redirect(url_for("admin_accounts"))

@app.route("/admin/students/delete-acc/<int:student_id>", methods=["POST"])
def delete_student_account_route(student_id):
    if not session.get("is_admin"):
        return redirect(url_for("login"))

    db.delete_student(student_id)
    flash("🗑️ Öğrenci hesabı ve şifresi silindi.", "success")
    return redirect(url_for("admin_accounts"))

# --- ÖĞRENCİ ÖZEL PANELİ ---

@app.route("/ogrenci/panel")
def student_dashboard():
    """Öğrencinin kendi devamsızlık karnesini, ders programını ve duyuruları gördüğü özel panel."""
    student = session.get("student")
    if not student:
        flash("Öğrenci panelini görüntülemek için lütfen öğrenci girişi yapınız.", "warning")
        return redirect(url_for("login", type="student"))

    student_stats = db.get_student_detail_stats(student["name"])
    schedules = db.get_all_schedules()
    announcements = db.get_active_announcements()
    course_name = db.get_setting("course_name", "Kurs Yoklama Sistemi")

    return render_template(
        "student_dashboard.html",
        student=student,
        stats=student_stats,
        schedules=schedules,
        announcements=announcements,
        course_name=course_name,
        format_date_tr=format_date_tr
    )

@app.route("/ogrenci/sifre-degistir", methods=["POST"])
def student_change_password():
    """Öğrencinin kendi şifresini değiştirmesini sağlar."""
    student = session.get("student")
    if not student:
        return redirect(url_for("login"))

    new_password = request.form.get("new_password", "").strip()
    if not new_password or len(new_password) < 3:
        flash("Şifre en az 3 karakter olmalıdır.", "danger")
        return redirect(url_for("student_dashboard"))

    if db.update_student_password(student["id"], new_password):
        student["password"] = new_password
        session["student"] = student
        flash("🎉 Şifreniz başarıyla güncellendi! Yeni şifrenizle giriş yapabilirsiniz.", "success")
    else:
        flash("Şifre güncellenirken bir hata oluştu.", "danger")

    return redirect(url_for("student_dashboard"))

# --- HAFTALIK DERS & ETÜT PROGRAMI YÖNETİMİ ---

@app.route("/admin/program")
def admin_schedule():
    """Haftalık ders ve etüt programı yönetimi."""
    if not session.get("is_admin"):
        return redirect(url_for("login"))

    schedules = db.get_all_schedules()
    course_name = db.get_setting("course_name", "Kurs Yoklama Sistemi")
    current_user = session.get("user", {})

    return render_template(
        "schedule.html",
        schedules=schedules,
        course_name=course_name,
        current_user=current_user
    )

@app.route("/admin/program/add", methods=["POST"])
def add_schedule_route():
    if not session.get("is_admin"):
        return redirect(url_for("login"))

    day_of_week = request.form.get("day_of_week", "Pazartesi")
    lesson_name = request.form.get("lesson_name", "").strip()
    teacher_name = request.form.get("teacher_name", "").strip()
    start_time = request.form.get("start_time", "17:00").strip()
    end_time = request.form.get("end_time", "18:30").strip()
    classroom = request.form.get("classroom", "Ana Derslik").strip()
    note = request.form.get("note", "").strip()

    if lesson_name:
        db.add_schedule(day_of_week, lesson_name, teacher_name, start_time, end_time, classroom, note)
        flash(f"📅 {day_of_week} günü için '{lesson_name}' dersi programa eklendi.", "success")
    else:
        flash("Ders adı zorunludur.", "danger")

    return redirect(url_for("admin_schedule"))

@app.route("/admin/program/delete/<int:schedule_id>", methods=["POST"])
def delete_schedule_route(schedule_id):
    if not session.get("is_admin"):
        return redirect(url_for("login"))

    db.delete_schedule(schedule_id)
    flash("Ders programdan silindi.", "info")
    return redirect(url_for("admin_schedule"))

# --- YÖNETİCİ PANELİ ---

@app.route("/admin")
def admin_dashboard():
    if not session.get("is_admin"):
        return redirect(url_for("login"))

    # Seçili tarih (varsayılan: bugün veya URL parametresi)
    selected_date = request.args.get("date", get_default_date())
    selected_date_display = format_date_tr(selected_date)

    # İstatistikler ve kayıtlar
    stats = db.get_stats_for_date(selected_date)
    attendances = db.get_attendances_by_date(selected_date)
    unique_dates = db.get_unique_dates()
    
    # Eğer seçili tarih listede yoksa listeye dahil et
    if selected_date not in unique_dates:
        unique_dates.insert(0, selected_date)

    course_name = db.get_setting("course_name", "Kurs Yoklama Sistemi")
    current_user = session.get("user", {})
    risk_students = db.get_absenteeism_risk_students()
    schedules = db.get_all_schedules()

    return render_template(
        "admin.html",
        selected_date=selected_date,
        selected_date_display=selected_date_display,
        stats=stats,
        attendances=attendances,
        unique_dates=unique_dates,
        format_date_tr=format_date_tr,
        course_name=course_name,
        current_user=current_user,
        risk_students=risk_students,
        schedules=schedules
    )

@app.route("/admin/delete/<int:attendance_id>", methods=["POST"])
def delete_attendance_route(attendance_id):
    if not session.get("is_admin"):
        return redirect(url_for("login"))

    date_param = request.form.get("date", get_default_date())
    db.delete_attendance(attendance_id)
    flash("Yoklama kaydı silindi.", "success")
    return redirect(url_for("admin_dashboard", date=date_param))

@app.route("/admin/export-csv")
def export_csv():
    """Seçili tarihteki yoklama listesini Excel uyumlu CSV formatında indirir."""
    if not session.get("is_admin"):
        return redirect(url_for("login"))

    selected_date = request.args.get("date", get_default_date())
    attendances = db.get_attendances_by_date(selected_date)
    
    output = io.StringIO()
    # Excel'in Türkçe karakterleri düzgün tanıması için UTF-8 BOM
    output.write("\ufeff")
    
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["Tarih", "Öğrenci Adı Soyadı", "Öğrenci No", "Telefon", "Katılım Durumu", "Mazeret / Açıklama", "Bildirim Zamanı"])
    
    status_map = {
        "geliyorum": "Geliyorum",
        "gelemiyorum": "Gelemeyeceğim",
        "gec_kalacagim": "Geç Kalacağım"
    }

    for a in attendances:
        writer.writerow([
            a["target_date"],
            a["student_name"],
            a.get("student_no", ""),
            a.get("phone", ""),
            status_map.get(a["status"], a["status"]),
            a.get("excuse", ""),
            a["created_at"]
        ])

    csv_data = output.getvalue().encode("utf-8-sig")
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename=yoklama_{selected_date}.csv"}
    )

# --- ÖĞRENCİ LİSTESİ YÖNETİMİ ---

@app.route("/admin/ogrenciler")
def admin_students():
    if not session.get("is_admin"):
        return redirect(url_for("login"))

    students = db.get_all_students()
    return render_template("students.html", students=students)

@app.route("/admin/ogrenciler/add", methods=["POST"])
def add_student_route():
    if not session.get("is_admin"):
        return redirect(url_for("login"))

    name = request.form.get("name", "").strip()
    student_no = request.form.get("student_no", "").strip()
    phone = request.form.get("phone", "").strip()

    if name:
        if db.add_student(name, student_no, phone):
            flash(f"'{name}' isimli öğrenci başarıyla eklendi.", "success")
        else:
            flash(f"'{name}' isimli öğrenci zaten kayıtlı!", "warning")
    else:
        flash("Öğrenci adı boş bırakılamaz.", "danger")

    return redirect(url_for("admin_students"))

@app.route("/admin/ogrenciler/delete/<int:student_id>", methods=["POST"])
def delete_student_route(student_id):
    if not session.get("is_admin"):
        return redirect(url_for("login"))

    db.delete_student(student_id)
    flash("Öğrenci listeden silindi.", "success")
    return redirect(url_for("admin_students"))

# --- CANLI SINIF YOKLAMASI ALMA ---

@app.route("/admin/yoklama-al", methods=["GET", "POST"])
def take_attendance():
    if not session.get("is_admin"):
        return redirect(url_for("login"))

    selected_date = request.args.get("date", get_default_date())
    
    if request.method == "POST":
        selected_date = request.form.get("target_date", get_default_date())
        student_names = request.form.getlist("student_names[]")
        
        records = []
        for name in student_names:
            status = request.form.get(f"status_{name}", "geldi")
            note = request.form.get(f"note_{name}", "")
            records.append({
                "student_name": name,
                "status": status,
                "note": note
            })
            
        db.save_bulk_class_attendance(selected_date, records)
        flash(f"{format_date_tr(selected_date)} sınıf yoklaması başarıyla kaydedildi.", "success")
        return redirect(url_for("take_attendance", date=selected_date))

    students_data = db.get_students_with_pre_declarations(selected_date)
    selected_date_display = format_date_tr(selected_date)
    course_name = db.get_setting("course_name", "Kurs Yoklama Sistemi")
    current_user = session.get("user", {})

    return render_template(
        "take_attendance.html",
        selected_date=selected_date,
        selected_date_display=selected_date_display,
        students_data=students_data,
        course_name=course_name,
        current_user=current_user
    )

# --- TOPLU ÖĞRENCİ EKLEME ---

@app.route("/admin/ogrenciler/bulk-add", methods=["POST"])
def bulk_add_students_route():
    if not session.get("is_admin"):
        return redirect(url_for("login"))

    raw_text = request.form.get("raw_text", "").strip()
    if raw_text:
        count = db.add_bulk_students(raw_text)
        flash(f"{count} adet öğrenci başarıyla listeye eklendi.", "success")
    else:
        flash("Lütfen eklenecek öğrenci listesini giriniz.", "warning")

    return redirect(url_for("admin_students"))

# --- ÖĞRENCİ DETAY DEVAMSIZLIK KARNESİ ---

@app.route("/admin/ogrenci/<student_name>")
def student_detail(student_name):
    if not session.get("is_admin"):
        return redirect(url_for("login"))

    stats = db.get_student_detail_stats(student_name)
    course_name = db.get_setting("course_name", "Kurs Yoklama Sistemi")
    return render_template(
        "student_detail.html",
        stats=stats,
        student_name=student_name,
        course_name=course_name,
        format_date_tr=format_date_tr
    )

# --- DUYURULAR YÖNETİMİ ---

@app.route("/admin/duyurular")
def admin_announcements():
    if not session.get("is_admin"):
        return redirect(url_for("login"))

    announcements = db.get_all_announcements()
    return render_template("announcements.html", announcements=announcements)

@app.route("/admin/duyurular/add", methods=["POST"])
def add_announcement_route():
    if not session.get("is_admin"):
        return redirect(url_for("login"))

    title = request.form.get("title", "").strip()
    content = request.form.get("content", "").strip()
    badge = request.form.get("badge", "Duyuru").strip()

    if title and content:
        db.add_announcement(title, content, badge)
        flash("Yeni duyuru yayınlandı.", "success")
    else:
        flash("Başlık ve duyuru metni zorunludur.", "danger")

    return redirect(url_for("admin_announcements"))

@app.route("/admin/duyurular/delete/<int:announcement_id>", methods=["POST"])
def delete_announcement_route(announcement_id):
    if not session.get("is_admin"):
        return redirect(url_for("login"))

    db.delete_announcement(announcement_id)
    flash("Duyuru silindi.", "success")
    return redirect(url_for("admin_announcements"))

@app.route("/admin/duyurular/toggle/<int:announcement_id>", methods=["POST"])
def toggle_announcement_route(announcement_id):
    if not session.get("is_admin"):
        return redirect(url_for("login"))

    db.toggle_announcement(announcement_id)
    flash("Duyuru durumu güncellendi.", "info")
    return redirect(url_for("admin_announcements"))

# --- YAZDIRILABİLİR RESMİ YOKLAMA ÇİZELGESİ (A4) ---

@app.route("/admin/yazdir")
def print_attendance_sheet():
    if not session.get("is_admin"):
        return redirect(url_for("login"))

    selected_date = request.args.get("date", get_default_date())
    selected_date_display = format_date_tr(selected_date)
    students_data = db.get_students_with_pre_declarations(selected_date)
    course_name = db.get_setting("course_name", "Kurs Yoklama Sistemi")

    return render_template(
        "print_sheet.html",
        selected_date=selected_date,
        selected_date_display=selected_date_display,
        students_data=students_data,
        course_name=course_name
    )

# --- QR KOD İLE HIZLI YOKLAMA EKRANI ---

@app.route("/admin/qr")
def qr_code_page():
    if not session.get("is_admin"):
        return redirect(url_for("login"))

    local_ip = get_local_ip()
    port = 5000
    mobile_url = f"http://{local_ip}:{port}"
    course_name = db.get_setting("course_name", "Kurs Yoklama Sistemi")

    return render_template(
        "qr.html",
        mobile_url=mobile_url,
        course_name=course_name
    )

# --- GRAFİK JSON API (Chart.js) ---

@app.route("/api/chart-data")
def api_chart_data():
    if not session.get("is_admin"):
        return jsonify({"error": "Unauthorized"}), 401

    data = db.get_recent_analytics_data(limit=7)
    return jsonify(data)

# --- AYARLAR ---

@app.route("/admin/settings", methods=["POST"])
def update_settings():
    if not session.get("is_admin"):
        return redirect(url_for("login"))

    course_name = request.form.get("course_name", "").strip()
    new_password = request.form.get("admin_password", "").strip()

    if course_name:
        db.set_setting("course_name", course_name)
    if new_password:
        db.set_setting("admin_password", new_password)
        flash("Ayarlar ve şifre güncellendi.", "success")
    else:
        flash("Ayarlar güncellendi.", "success")

    return redirect(url_for("admin_dashboard"))

if __name__ == "__main__":
    local_ip = get_local_ip()
    port = 5000
    print("\n" + "="*60)
    print("🚀 KURS YOKLAMA VE MAZERET BİLDİRİM SİSTEMİ ÇALIŞIYOR!")
    print("="*60)
    print(f"👉 Bilgisayarınızdan Giriş: http://localhost:{port}")
    print(f"👉 Aynı Ağdaki Telefonlardan / Öğrencilerden Giriş: http://{local_ip}:{port}")
    print(f"👉 Öğretmen/Yönetici Paneli: http://localhost:{port}/admin (Şifre: admin123)")
    print("="*60 + "\n")
    
    app.run(host="0.0.0.0", port=port, debug=True)
