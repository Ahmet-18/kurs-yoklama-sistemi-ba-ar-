import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kurs_yoklama.db")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# --- ESNEK METİN VE ŞİFRE NORMALİZASYONU (BÜYÜK/KÜÇÜK HARF, BİTİŞİK/AYRIK TOLERANSI) ---

def normalize_text(text):
    """
    Metinleri karşılaştırma için normalize eder:
    - Baştaki, sondaki ve aradaki tüm boşlukları kaldırır ('ahmet yilmaz' -> 'ahmetyilmaz')
    - Türkçe harfleri İngilizce benzerlerine dönüştürür (ç->c, ğ->g, ı/i->i, ö->o, ş->s, ü->u)
    - Büyük/küçük harf farkını ortadan kaldırır ('AHMET' -> 'ahmet')
    - Noktalama veya ayraçları temizler
    """
    if text is None:
        return ""
    s = str(text).strip()
    
    tr_map = {
        'İ': 'i', 'I': 'i', 'ı': 'i',
        'Ş': 's', 'ş': 's',
        'Ğ': 'g', 'ğ': 'g',
        'Ü': 'u', 'ü': 'u',
        'Ö': 'o', 'ö': 'o',
        'Ç': 'c', 'ç': 'c'
    }
    for k, v in tr_map.items():
        s = s.replace(k, v)
        
    s = s.lower()
    # Harf ve rakamlar dışındaki tüm boşluk ve karakterleri at
    return "".join(c for c in s if c.isalnum())

def passwords_match(input_pass, stored_pass):
    """
    Şifre girişlerini esnek ve hatasız biçimde kontrol eder:
    - Birebir eşleşme
    - Küçük harf / büyük harf duyarsız eşleşme ('Admin123' == 'admin123')
    - Boşluksuz / bitişik-ayrık eşleşme ('123 456' == '123456')
    - Türkçe karakter toleranslı normalize eşleşme
    """
    if input_pass is None or stored_pass is None:
        return False
    
    inp_raw = str(input_pass).strip()
    sto_raw = str(stored_pass).strip()
    
    # 1. Birebir eşitlik
    if inp_raw == sto_raw:
        return True
    
    # 2. Küçük / büyük harf eşitliği
    if inp_raw.lower() == sto_raw.lower():
        return True
        
    # 3. Boşlukları temizleyerek kontrol (bitişik / ayrık toleransı)
    if "".join(inp_raw.split()) == "".join(sto_raw.split()):
        return True

    # 4. Boşluksuz + küçük harf kontrolü
    if "".join(inp_raw.lower().split()) == "".join(sto_raw.lower().split()):
        return True

    # 5. Tam normalize kontrol (Türkçe karakterler dahil)
    norm_inp = normalize_text(inp_raw)
    norm_sto = normalize_text(sto_raw)
    if norm_inp and norm_inp == norm_sto:
        return True
        
    return False

def identifiers_match(input_val, stored_val):
    """
    Kullanıcı adı, öğrenci adı veya numara karşılaştırması:
    - Birebir eşitlik
    - Boşluksuz ve küçük harf eşitliği ('keremyilmaz' == 'Kerem Yılmaz')
    - Türkçe karakter toleranslı normalize eşitlik ('Ahmet Yilmaz' == 'Ahmet Yılmaz')
    """
    if input_val is None or stored_val is None:
        return False
        
    inp_raw = str(input_val).strip()
    sto_raw = str(stored_val).strip()
    
    if inp_raw == sto_raw:
        return True
        
    if inp_raw.lower() == sto_raw.lower():
        return True
        
    norm_inp = normalize_text(inp_raw)
    norm_sto = normalize_text(sto_raw)
    if norm_inp and norm_inp == norm_sto:
        return True
        
    return False

def init_db():
    """Veritabanı tablolarını oluşturur ve varsayılan ayarları yükler."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Yoklama bildirimleri tablosu
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS attendances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_name TEXT NOT NULL,
            student_no TEXT,
            target_date TEXT NOT NULL,
            status TEXT NOT NULL,
            excuse TEXT,
            phone TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Kayıtlı öğrenciler tablosu
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            student_no TEXT,
            phone TEXT,
            password TEXT DEFAULT '123456',
            last_login TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Öğrenciler tablosu sütun migrasyonları
    try:
        cursor.execute("ALTER TABLE students ADD COLUMN password TEXT DEFAULT '123456'")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE students ADD COLUMN last_login TIMESTAMP")
    except sqlite3.OperationalError:
        pass

    # Öğretmenin aldığı resmi sınıf yoklama tablosu
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS class_attendances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_name TEXT NOT NULL,
            target_date TEXT NOT NULL,
            status TEXT NOT NULL, -- 'geldi', 'gelmedi', 'gec_geldi', 'mazeretli'
            note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(student_name, target_date)
        )
    """)

    # Duyurular tablosu
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS announcements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            badge TEXT DEFAULT 'Duyuru',
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Öğretmen, Yönetici ve Kullanıcı Hesapları Tablosu
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS teachers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            full_name TEXT NOT NULL,
            subject TEXT DEFAULT 'Genel',
            role TEXT DEFAULT 'teacher', -- 'admin' veya 'teacher' veya 'user'
            last_login TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # last_login sütunu daha önceden açılmış tablolara ekleme (varsa hata vermez)
    try:
        cursor.execute("ALTER TABLE teachers ADD COLUMN last_login TIMESTAMP")
    except sqlite3.OperationalError:
        pass

    # Sisteme Giriş Yapanlar / Giriş Geçmişi Log Tablosu
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS login_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            full_name TEXT,
            role TEXT,
            ip_address TEXT,
            status TEXT DEFAULT 'Başarılı',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Ayarlar tablosu (Yönetici şifresi vb.)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    # Varsayılan yönetici ve örnek öğretmen hesapları
    cursor.execute("""
        INSERT OR IGNORE INTO teachers (id, username, password, full_name, subject, role)
        VALUES (1, 'admin', 'admin123', 'Boş İşler Müdürü', 'Yönetim', 'admin')
    """)
    # Var olan veritabanında Kurum Yöneticisi kaydı varsa Boş İşler Müdürü olarak güncelle
    cursor.execute("""
        UPDATE teachers 
        SET full_name = 'Boş İşler Müdürü' 
        WHERE id = 1 OR username = 'admin' OR full_name = 'Kurum Yöneticisi'
    """)
    cursor.execute("""
        UPDATE login_logs 
        SET full_name = 'Boş İşler Müdürü' 
        WHERE full_name = 'Kurum Yöneticisi'
    """)
    cursor.execute("""
        INSERT OR IGNORE INTO teachers (id, username, password, full_name, subject, role)
        VALUES (2, 'ogretmen', '123456', 'Örnek Öğretmen', 'Matematik', 'teacher')
    """)

    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('course_name', 'Kurs Yoklama ve Mazeret Sistemi')")
    
    # Haftalık Ders & Etüt Programı Tablosu
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            day_of_week TEXT NOT NULL,
            day_order INTEGER DEFAULT 1,
            lesson_name TEXT NOT NULL,
            teacher_name TEXT,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            classroom TEXT DEFAULT 'Ana Derslik',
            note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Eğer program tablosu boşsa örnek dersleri ekle
    cursor.execute("SELECT COUNT(*) FROM schedules")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
            INSERT INTO schedules (day_of_week, day_order, lesson_name, teacher_name, start_time, end_time, classroom, note)
            VALUES 
            ('Pazartesi', 1, 'Matematik (TYT / AYT)', 'Örnek Öğretmen', '17:00', '18:30', 'Derslik 1', 'Problem çözümü ve konu tekrarı'),
            ('Çarşamba', 3, 'Fizik & Fen Bilimleri', 'Boş İşler Müdürü', '17:00', '18:30', 'Derslik 2', 'Kuvvet ve Hareket testleri'),
            ('Cuma', 5, 'Türkçe & Paragraf Kampı', 'Örnek Öğretmen', '16:30', '18:00', 'Derslik 1', 'Hızlı okuma ve deneme çözümü'),
            ('Cumartesi', 6, 'Genel TYT Deneme Sınavı', 'Tüm Eğitmenler', '10:00', '13:00', 'Konferans Salonu', 'Optik form ile gerçek sınav provası')
        """)

    # Eski varsayılan örnek duyuruyu temizle (Varsa)
    cursor.execute("DELETE FROM announcements WHERE id = 1 AND title = 'Haftalık Kurs Programı Hakkında'")

    conn.commit()
    conn.close()

def save_or_update_attendance(student_name, student_no, target_date, status, excuse, phone=""):
    """
    Öğrencinin yoklama bildirimini kaydeder.
    Aynı öğrenci aynı tarih için tekrar bildirim yaparsa kaydını günceller.
    """
    student_name = student_name.strip()
    student_no = (student_no or "").strip()
    excuse = (excuse or "").strip()
    phone = (phone or "").strip()

    conn = get_db_connection()
    cursor = conn.cursor()

    # Aynı öğrenci aynı tarih için daha önce göndermiş mi kontrol et (büyük/küçük harf, bitişik/ayrık toleranslı)
    cursor.execute("""
        SELECT id, student_name FROM attendances 
        WHERE target_date = ?
    """, (target_date,))
    existing_rows = cursor.fetchall()
    existing_id = None
    for row in existing_rows:
        if identifiers_match(student_name, row["student_name"]):
            existing_id = row["id"]
            break

    if existing_id:
        cursor.execute("""
            UPDATE attendances 
            SET student_name = ?, student_no = ?, status = ?, excuse = ?, phone = ?, created_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (student_name, student_no, status, excuse, phone, existing_id))
        attendance_id = existing_id
    else:
        cursor.execute("""
            INSERT INTO attendances (student_name, student_no, target_date, status, excuse, phone)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (student_name, student_no, target_date, status, excuse, phone))
        attendance_id = cursor.lastrowid

    conn.commit()
    conn.close()
    return attendance_id

def get_attendances_by_date(target_date):
    """Belirli bir tarihteki tüm bildirimleri getirir."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM attendances 
        WHERE target_date = ? 
        ORDER BY created_at DESC
    """, (target_date,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_stats_for_date(target_date):
    """Belirli bir tarih için özet sayıları hesaplar."""
    attendances = get_attendances_by_date(target_date)
    registered_students = get_all_students()

    total_submitted = len(attendances)
    coming_count = sum(1 for a in attendances if a["status"] == "geliyorum")
    not_coming_count = sum(1 for a in attendances if a["status"] == "gelemiyorum")
    late_count = sum(1 for a in attendances if a["status"] == "gec_kalacagim")

    # Bildirim yapan öğrencilerin isimleri (küçük harf normalize)
    submitted_names = {a["student_name"].strip().lower() for a in attendances}
    
    # Kayıtlı olup henüz bildirmeyenler
    missing_students = [
        s for s in registered_students 
        if s["name"].strip().lower() not in submitted_names
    ]

    return {
        "total_submitted": total_submitted,
        "coming_count": coming_count,
        "not_coming_count": not_coming_count,
        "late_count": late_count,
        "total_registered": len(registered_students),
        "missing_count": len(missing_students),
        "missing_students": missing_students
    }

def get_unique_dates():
    """Sistemde kaydı olan tüm tarihleri listeler (en yeniden eskiye)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT target_date FROM attendances 
        ORDER BY target_date DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [row["target_date"] for row in rows]

def delete_attendance(attendance_id):
    """Bildirim kaydını siler."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM attendances WHERE id = ?", (attendance_id,))
    conn.commit()
    conn.close()

# Öğrenci Listesi & Hesap Yönetimi
def get_all_students():
    """Kayıtlı tüm öğrencileri şifreleriyle birlikte listeler."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, student_no, phone, 
               COALESCE(password, '123456') as password, 
               last_login, created_at 
        FROM students 
        ORDER BY name ASC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_student_by_id(student_id):
    """ID'ye göre öğrenciyi döner."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM students WHERE id = ?", (student_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_student_by_name(name):
    """İsme göre öğrenciyi döner (Büyük/küçük, bitişik/ayrık ve Türkçe karakter duyarsız)."""
    if not name:
        return None
    name_clean = str(name).strip()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM students WHERE LOWER(TRIM(name)) = LOWER(TRIM(?))", (name_clean,))
    row = cursor.fetchone()
    if row:
        conn.close()
        return dict(row)

    # Esnek normalizasyon ile arama
    cursor.execute("SELECT * FROM students")
    rows = cursor.fetchall()
    conn.close()

    for r in rows:
        if identifiers_match(name_clean, r["name"]):
            return dict(r)

    return None

def add_student(name, student_no="", phone="", password=""):
    """Öğrenci listesine yeni öğrenci ve şifresini ekler."""
    name = name.strip()
    if not name:
        return False
    password = password.strip() if password else "123456"
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO students (name, student_no, phone, password)
            VALUES (?, ?, ?, ?)
        """, (name, (student_no or "").strip(), (phone or "").strip(), password))
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False
    finally:
        conn.close()
    return success

def update_student(student_id, name, student_no="", phone="", password=""):
    """Öğrencinin bilgilerini ve şifresini günceller."""
    name = name.strip()
    if not name:
        return False
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if password and password.strip():
            cursor.execute("""
                UPDATE students 
                SET name = ?, student_no = ?, phone = ?, password = ?
                WHERE id = ?
            """, (name, (student_no or "").strip(), (phone or "").strip(), password.strip(), student_id))
        else:
            cursor.execute("""
                UPDATE students 
                SET name = ?, student_no = ?, phone = ?
                WHERE id = ?
            """, (name, (student_no or "").strip(), (phone or "").strip(), student_id))
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False
    finally:
        conn.close()
    return success

def delete_student(student_id):
    """Öğrenciyi listeden siler."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM students WHERE id = ?", (student_id,))
    conn.commit()
    conn.close()

def authenticate_student(identifier, password):
    """
    Öğrenci girişi doğrulaması:
    Öğrenci Numarası, Ad Soyad veya Telefon ile şifreyi doğrular.
    Büyük/küçük harf, bitişik/ayrık yazım ve Türkçe karakter hatalarını tolere eder.
    """
    if not identifier or not password:
        return None

    identifier_clean = str(identifier).strip()
    password_clean = str(password).strip()

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, student_no, phone, 
               COALESCE(password, '123456') as password, 
               last_login, created_at 
        FROM students
    """)
    rows = cursor.fetchall()
    conn.close()

    for r in rows:
        r_dict = dict(r)
        r_name = r_dict.get("name", "")
        r_no = r_dict.get("student_no", "")
        r_phone = r_dict.get("phone", "")
        r_pass = r_dict.get("password", "123456")

        # 1. Kimlik eşleşiyor mu? (Ad Soyad, Öğrenci No veya Telefon)
        id_matched = (
            identifiers_match(identifier_clean, r_name) or
            identifiers_match(identifier_clean, r_no) or
            identifiers_match(identifier_clean, r_phone)
        )

        # 2. Şifre eşleşiyor mu? (Büyük/küçük harf, bitişik/ayrık, boşluksuz vb.)
        if id_matched and passwords_match(password_clean, r_pass):
            return r_dict

    return None

def update_student_last_login(student_id):
    """Öğrencinin son giriş zamanını günceller."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE students 
        SET last_login = CURRENT_TIMESTAMP 
        WHERE id = ?
    """, (student_id,))
    conn.commit()
    conn.close()

# Ayarlar
def get_setting(key, default=""):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row["value"] if row else default

def set_setting(key, value):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
    """, (key, value))
    conn.commit()
    conn.close()

# --- ÖĞRETMEN RESMİ SINIF YOKLAMASI İŞLEMLERİ ---

def save_bulk_class_attendance(target_date, records):
    """
    Öğretmenin aldığı sınıf yoklamasını topluca kaydeder/günceller.
    records: list of dicts [{'student_name': '...', 'status': 'geldi'/'gelmedi'/'gec_geldi'/'mazeretli', 'note': '...'}]
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    for r in records:
        name = r.get("student_name", "").strip()
        status = r.get("status", "geldi").strip()
        note = r.get("note", "").strip()
        if not name:
            continue

        cursor.execute("""
            INSERT INTO class_attendances (student_name, target_date, status, note)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(student_name, target_date) DO UPDATE SET
                status = excluded.status,
                note = excluded.note,
                created_at = CURRENT_TIMESTAMP
        """, (name, target_date, status, note))

    conn.commit()
    conn.close()

def get_class_attendance_for_date(target_date):
    """Belirli bir günün resmi sınıf yoklamasını döner."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM class_attendances 
        WHERE target_date = ? 
        ORDER BY student_name ASC
    """, (target_date,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_students_with_pre_declarations(target_date):
    """
    Öğretmenin yoklama alma ekranı için:
    Tüm kayıtlı öğrencileri, önceden gönderdikleri bildirim/mazeret durumlarını
    ve varsa kaydedilmiş resmi yoklama durumlarını tek listede birleştirir.
    """
    registered_students = get_all_students()
    pre_declarations = get_attendances_by_date(target_date)
    saved_class_att = get_class_attendance_for_date(target_date)

    # Sözlük indeksleri
    pre_map = {p["student_name"].strip().lower(): p for p in pre_declarations}
    saved_map = {s["student_name"].strip().lower(): s for s in saved_class_att}

    combined_list = []
    
    # 1. Kayıtlı öğrenciler
    seen_names = set()
    for st in registered_students:
        name_key = st["name"].strip().lower()
        seen_names.add(name_key)
        
        pre = pre_map.get(name_key)
        saved = saved_map.get(name_key)
        
        # Varsayılan yoklama durumu: Eğer öğretmen daha önce kaydetmişse o, yoksa ön bildirim, o da yoksa 'geldi'
        if saved:
            current_status = saved["status"]
            current_note = saved["note"]
        elif pre:
            if pre["status"] == "geliyorum":
                current_status = "geldi"
            elif pre["status"] == "gelemiyorum":
                current_status = "mazeretli"
            elif pre["status"] == "gec_kalacagim":
                current_status = "gec_geldi"
            else:
                current_status = "geldi"
            current_note = pre.get("excuse", "")
        else:
            current_status = "geldi"
            current_note = ""

        combined_list.append({
            "name": st["name"],
            "student_no": st.get("student_no", ""),
            "phone": st.get("phone", ""),
            "pre_declaration": pre,  # Öğrencinin önceden gönderdiği durum/mazeret
            "current_status": current_status,  # 'geldi', 'gelmedi', 'gec_geldi', 'mazeretli'
            "current_note": current_note
        })

    # 2. Kayıtlı listede olmayıp formdan doğrudan isim yazarak bildirenler varsa onları da ekle
    for pre in pre_declarations:
        name_key = pre["student_name"].strip().lower()
        if name_key not in seen_names:
            seen_names.add(name_key)
            saved = saved_map.get(name_key)
            
            if saved:
                current_status = saved["status"]
                current_note = saved["note"]
            else:
                if pre["status"] == "geliyorum":
                    current_status = "geldi"
                elif pre["status"] == "gelemiyorum":
                    current_status = "mazeretli"
                elif pre["status"] == "gec_kalacagim":
                    current_status = "gec_geldi"
                else:
                    current_status = "geldi"
                current_note = pre.get("excuse", "")

            combined_list.append({
                "name": pre["student_name"],
                "student_no": pre.get("student_no", ""),
                "phone": pre.get("phone", ""),
                "pre_declaration": pre,
                "current_status": current_status,
                "current_note": current_note
            })

    return combined_list

# --- DUYURU YÖNETİMİ ---

def get_active_announcements():
    """Öğrencilerin gördüğü aktif duyuruları listeler."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM announcements WHERE is_active = 1 ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_all_announcements():
    """Tüm duyuruları listeler (Admin için)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM announcements ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def add_announcement(title, content, badge="Duyuru"):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO announcements (title, content, badge, is_active)
        VALUES (?, ?, ?, 1)
    """, (title.strip(), content.strip(), badge.strip()))
    conn.commit()
    conn.close()

def delete_announcement(announcement_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM announcements WHERE id = ?", (announcement_id,))
    conn.commit()
    conn.close()

def toggle_announcement(announcement_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE announcements SET is_active = 1 - is_active WHERE id = ?", (announcement_id,))
    conn.commit()
    conn.close()

# --- TOPLU ÖĞRENCİ EKLEME ---

def add_bulk_students(raw_text):
    """
    Kullanıcının her satıra bir öğrenci yazdığı metni ayrıştırıp veritabanına ekler.
    Desteklenen formatlar:
    Ahmet Yılmaz
    Ayşe Kaya, 102, 05551234567
    Mehmet Demir - 105
    """
    lines = raw_text.strip().split("\n")
    added_count = 0
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        parts = []
        if "," in line:
            parts = [p.strip() for p in line.split(",")]
        elif "-" in line:
            parts = [p.strip() for p in line.split("-")]
        else:
            parts = [line]

        name = parts[0]
        student_no = parts[1] if len(parts) > 1 else ""
        phone = parts[2] if len(parts) > 2 else ""

        if name:
            if add_student(name, student_no, phone):
                added_count += 1

    return added_count

# --- ÖĞRENCİ DETAYLI DEVAMSIZLIK KARNESİ ---

def get_student_detail_stats(student_name):
    """
    Belirli bir öğrencinin geçmişteki tüm yoklamalarını,
    mazeret bildirimlerini ve katılım yüzdesini hesaplar.
    """
    student_name = student_name.strip()
    conn = get_db_connection()
    cursor = conn.cursor()

    # Öğrenci temel bilgileri
    cursor.execute("SELECT * FROM students WHERE LOWER(TRIM(name)) = LOWER(?)", (student_name,))
    student_info = cursor.fetchone()

    # Resmi sınıf yoklama kayıtları
    cursor.execute("""
        SELECT * FROM class_attendances 
        WHERE LOWER(TRIM(student_name)) = LOWER(?) 
        ORDER BY target_date DESC
    """, (student_name,))
    class_records = [dict(r) for r in cursor.fetchall()]

    # Önceden gönderdiği mazeret/durum bildirimleri
    cursor.execute("""
        SELECT * FROM attendances 
        WHERE LOWER(TRIM(student_name)) = LOWER(?) 
        ORDER BY target_date DESC
    """, (student_name,))
    declaration_records = [dict(r) for r in cursor.fetchall()]

    conn.close()

    total_days = len(class_records)
    present_days = sum(1 for r in class_records if r["status"] == "geldi")
    absent_days = sum(1 for r in class_records if r["status"] == "gelmedi")
    excused_days = sum(1 for r in class_records if r["status"] == "mazeretli")
    late_days = sum(1 for r in class_records if r["status"] == "gec_geldi")

    rate = 0
    if total_days > 0:
        rate = round(((present_days + late_days) / total_days) * 100, 1)
    elif len(declaration_records) > 0:
        # Eğer resmi sınıf yoklaması henüz yoksa öğrencinin kendi bildirimlerinden hesapla
        total_days = len(declaration_records)
        present_days = sum(1 for r in declaration_records if r["status"] == "geliyorum")
        absent_days = sum(1 for r in declaration_records if r["status"] == "gelemiyorum")
        late_days = sum(1 for r in declaration_records if r["status"] == "gec_kalacagim")
        excused_days = sum(1 for r in declaration_records if r.get("excuse"))
        rate = round(((present_days + late_days) / total_days) * 100, 1)

    return {
        "student_info": dict(student_info) if student_info else {"name": student_name},
        "total_days": total_days,
        "present_days": present_days,
        "absent_days": absent_days,
        "excused_days": excused_days,
        "late_days": late_days,
        "attendance_rate": rate,
        "class_records": class_records,
        "declaration_records": declaration_records
    }

# --- KRİTİK DEVAMSIZLIK RİSKİ ANALİZİ ---

def get_absenteeism_risk_students(threshold=2):
    """
    2 veya daha fazla devamsızlığı olan veya katılım oranı %75'in altında olan riskli öğrencileri tespit eder.
    """
    all_students = get_all_students()
    risk_list = []
    for s in all_students:
        stats = get_student_detail_stats(s["name"])
        absent_count = stats["absent_days"]
        rate = stats["attendance_rate"]
        total = stats["total_days"]
        
        is_risk = False
        reasons = []
        if absent_count >= threshold:
            is_risk = True
            reasons.append(f"{absent_count} gün devamsız")
        if total >= 2 and rate < 75:
            is_risk = True
            reasons.append(f"%{rate} katılım")

        if is_risk:
            s_dict = dict(s)
            s_dict["stats"] = stats
            s_dict["total_absent"] = absent_count
            s_dict["attendance_rate"] = rate
            s_dict["risk_reasons"] = " • ".join(reasons)
            risk_list.append(s_dict)
            
    risk_list.sort(key=lambda x: x["stats"]["absent_days"], reverse=True)
    return risk_list

# --- HAFTALIK DERS & ETÜT PROGRAMI FONKSİYONLARI ---

DAY_ORDER = {
    "Pazartesi": 1,
    "Salı": 2,
    "Çarşamba": 3,
    "Perşembe": 4,
    "Cuma": 5,
    "Cumartesi": 6,
    "Pazar": 7
}

def get_all_schedules():
    """Haftalık ders programını gün ve saate göre sıralı döner."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM schedules 
        ORDER BY day_order ASC, start_time ASC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def add_schedule(day_of_week, lesson_name, teacher_name="", start_time="17:00", end_time="18:30", classroom="Ana Derslik", note=""):
    """Ders programına yeni ders/etüt ekler."""
    day_order = DAY_ORDER.get(day_of_week, 1)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO schedules (day_of_week, day_order, lesson_name, teacher_name, start_time, end_time, classroom, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (day_of_week.strip(), day_order, lesson_name.strip(), (teacher_name or "").strip(), start_time.strip(), end_time.strip(), (classroom or "Ana Derslik").strip(), (note or "").strip()))
    conn.commit()
    conn.close()
    return True

def delete_schedule(schedule_id):
    """Programdan ders siler."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
    conn.commit()
    conn.close()
    return True

def update_student_password(student_id, new_password):
    """Öğrencinin kendi şifresini güncellemesini sağlar."""
    if not new_password or not str(new_password).strip():
        return False
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE students SET password = ? WHERE id = ?", (str(new_password).strip(), student_id))
    conn.commit()
    conn.close()
    return True

# --- GRAFİK VE HAFTALIK ANALİTİK VERİSİ (Chart.js) ---

def get_recent_analytics_data(limit=7):
    """
    Son N günün katılım trendini Chart.js grafiği için hazırlar.
    """
    dates = get_unique_dates()[:limit]
    dates.reverse() # Kronolojik sıra

    labels = []
    coming_data = []
    not_coming_data = []

    for d in dates:
        stats = get_stats_for_date(d)
        # Tarihi kısa göster (Örn: 25 Ağu)
        try:
            dt = datetime.strptime(d, "%Y-%m-%d")
            short_label = f"{dt.day} {TR_MONTHS[dt.month][:3]} ({TR_DAYS[dt.weekday()][:3]})"
        except Exception:
            short_label = d

        labels.append(short_label)
        coming_data.append(stats["coming_count"])
        not_coming_data.append(stats["not_coming_count"])

    return {
        "labels": labels,
        "coming": coming_data,
        "not_coming": not_coming_data
    }

# --- TÜM KULLANICI HESAPLARI, ŞİFRELER VE GİRİŞ İŞLEMLERİ ---

def authenticate_teacher(username, password):
    """
    Kullanıcı adı ve şifreyi doğrular.
    Büyük/küçük harf, bitişik/ayrık yazım ve Türkçe karakter hatalarını tolere eder.
    Başarılıysa kullanıcı bilgilerini döner.
    """
    if not username or not password:
        return None

    username_clean = str(username).strip()
    password_clean = str(password).strip()

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, username, password, full_name, subject, role, last_login, created_at 
        FROM teachers
    """)
    rows = cursor.fetchall()
    conn.close()

    for r in rows:
        r_dict = dict(r)
        r_user = r_dict.get("username", "")
        r_name = r_dict.get("full_name", "")
        r_pass = r_dict.get("password", "")

        # 1. Kullanıcı adı veya Tam İsim eşleşiyor mu?
        user_matched = (
            identifiers_match(username_clean, r_user) or 
            identifiers_match(username_clean, r_name)
        )

        # 2. Şifre eşleşiyor mu?
        if user_matched and passwords_match(password_clean, r_pass):
            r_dict.pop("password", None)
            return r_dict

    return None

def get_all_accounts():
    """Tüm kayıtlı kullanıcı hesaplarını şifreleriyle birlikte listeler."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, username, password, full_name, subject, role, last_login, created_at 
        FROM teachers 
        ORDER BY 
            CASE role 
                WHEN 'admin' THEN 1 
                WHEN 'teacher' THEN 2 
                ELSE 3 
            END, 
            full_name ASC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_all_teachers():
    """Tüm öğretmen hesaplarını listeler."""
    return get_all_accounts()

def add_teacher(username, password, full_name, subject="Genel", role="teacher"):
    """Yeni kullanıcı / öğretmen / yönetici hesabı oluşturur."""
    username = username.strip().lower()
    password = password.strip()
    full_name = full_name.strip()
    subject = subject.strip() or "Genel"
    
    if not username or not password or not full_name:
        return False

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO teachers (username, password, full_name, subject, role)
            VALUES (?, ?, ?, ?, ?)
        """, (username, password, full_name, subject, role))
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False
    finally:
        conn.close()
    return success

def update_account(user_id, full_name, username, password, subject="Genel", role="teacher"):
    """Kullanıcının adını, kullanıcı adını, şifresini, branşını ve rolünü günceller."""
    full_name = full_name.strip()
    username = username.strip().lower()
    password = password.strip()
    subject = subject.strip() or "Genel"
    
    if not full_name or not username or not password:
        return False

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE teachers 
            SET full_name = ?, username = ?, password = ?, subject = ?, role = ?
            WHERE id = ?
        """, (full_name, username, password, subject, role, user_id))
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False
    finally:
        conn.close()
    return success

def delete_teacher(teacher_id):
    """Öğretmen / Kullanıcı hesabını siler (Ana yönetici ID 1 silinemez)."""
    if int(teacher_id) == 1:
        return False
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM teachers WHERE id = ?", (teacher_id,))
    conn.commit()
    conn.close()
    return True

def delete_account(user_id):
    return delete_teacher(user_id)

def update_teacher_profile(teacher_id, full_name, subject, new_password=None):
    """Kullanıcının kendi profilini/şifresini güncellemesini sağlar."""
    conn = get_db_connection()
    cursor = conn.cursor()
    if new_password and new_password.strip():
        cursor.execute("""
            UPDATE teachers 
            SET full_name = ?, subject = ?, password = ?
            WHERE id = ?
        """, (full_name.strip(), subject.strip(), new_password.strip(), teacher_id))
    else:
        cursor.execute("""
            UPDATE teachers 
            SET full_name = ?, subject = ?
            WHERE id = ?
        """, (full_name.strip(), subject.strip(), teacher_id))
    conn.commit()
    conn.close()

def update_last_login(user_id):
    """Kullanıcının sisteme son giriş yaptığı zamanı günceller."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE teachers 
        SET last_login = CURRENT_TIMESTAMP 
        WHERE id = ?
    """, (user_id,))
    conn.commit()
    conn.close()

# --- SİSTEME GİRİŞ YAPANLAR LOG / GEÇMİŞ İŞLEMLERİ ---

def log_login_attempt(username, full_name="", role="kullanıcı", ip_address="", status="Başarılı"):
    """Her giriş denemesini ve başarılı girişleri veritabanına kaydeder."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO login_logs (username, full_name, role, ip_address, status)
        VALUES (?, ?, ?, ?, ?)
    """, (username.strip(), full_name.strip(), role.strip(), ip_address.strip(), status.strip()))
    conn.commit()
    conn.close()

def get_login_logs(limit=60):
    """Son giriş yapan kişilerin ve denemelerin listesini döner."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, username, full_name, role, ip_address, status, created_at 
        FROM login_logs 
        ORDER BY id DESC 
        LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def clear_login_logs():
    """Giriş log geçmişini temizler."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM login_logs")
    conn.commit()
    conn.close()

# Modül yüklendiğinde tabloları ve güncellemeleri otomatik uygula
try:
    init_db()
except Exception:
    pass





