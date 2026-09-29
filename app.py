from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from functools import wraps
import os
import sqlite3
import secrets
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo
import resend

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(32))
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)

# Configuração de envio de confirmações de reserva/contacto via Resend
resend.api_key = os.environ.get("RESEND_API_KEY", "")
EMAIL_DESTINO = "marcocaldeira1987@gmail.com"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("BOOKINGS_DB_PATH", os.path.join(BASE_DIR, "bookings.db"))
OPENING_TIME = time(9, 0)
MORNING_END = time(13, 0)
AFTERNOON_START = time(14, 30)
CLOSING_TIME = time(19, 30)
LAST_BOOKING_START = time(18, 30)
BUSINESS_TZ = ZoneInfo("Europe/Lisbon")
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "https://pointfino.pt").rstrip("/")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

SERVICE_DURATIONS = {
    "Corte (12.00€)": 30,
    "Barba (7.00€)": 30,
    "Corte e Barba (16.00€)": 60,
    "Corte e Barboterapia (17.00€)": 60,
    "Barboterapia (8.00€)": 30,
    "Corte, Barba e Sobrancelha (18.00€)": 60,
    "Corte e Sobrancelha (14.00€)": 30,
    "Corte de máquina (9.00€)": 30,
    "Cera quente ouvido (4.00€)": 30,
    "Cera quente nariz (4.00€)": 30,
    "Cera quente nariz e ouvido (7.00€)": 60,
    "Esfoliação (5.00€)": 30,
    "Black Mask (7.00€)": 30,
    "Luzes (madeixas) (50.00€)": 150,
    "Platinado (50.00€)": 150,
    "Pigmentação cabelo (10.00€)": 30,
    "Pigmentação barba (10.00€)": 30,
    "Corte, barboterapia e sobrancelha (19.00€)": 60,
    "Mask Argan (7.00€)": 30,
}


def get_db():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    with get_db() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                service TEXT NOT NULL,
                barber TEXT NOT NULL,
                starts_at TEXT NOT NULL,
                ends_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'requested',
                cancel_token TEXT UNIQUE,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        columns = {row[1] for row in connection.execute("PRAGMA table_info(bookings)").fetchall()}
        if "cancel_token" not in columns:
            connection.execute("ALTER TABLE bookings ADD COLUMN cancel_token TEXT")
            connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_bookings_cancel_token ON bookings(cancel_token)")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_bookings_barber_time "
            "ON bookings(barber, starts_at, ends_at)"
        )


def business_now():
    return datetime.now(BUSINESS_TZ).replace(tzinfo=None)


def admin_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not session.get("admin_authenticated"):
            return redirect(url_for("admin_login", next=request.path))
        return view(*args, **kwargs)
    return wrapped_view


def parse_booking_start(raw_value):
    return datetime.strptime(raw_value, "%Y-%m-%dT%H:%M")


def is_opening_hours(start, end):
    if start.weekday() >= 6:
        return False
    morning_slot = start.time() >= OPENING_TIME and end.time() <= MORNING_END
    afternoon_slot = start.time() >= AFTERNOON_START and end.time() <= CLOSING_TIME
    return morning_slot or afternoon_slot


def get_booked_ranges(barber, selected_date):
    day_start = f"{selected_date}T00:00"
    day_end = f"{selected_date}T23:59"
    with get_db() as connection:
        rows = connection.execute(
            """SELECT starts_at, ends_at FROM bookings
               WHERE barber = ? AND status != 'cancelled'
               AND starts_at < ? AND ends_at > ?""",
            (barber, day_end, day_start),
        ).fetchall()
    return [(datetime.fromisoformat(row["starts_at"]), datetime.fromisoformat(row["ends_at"])) for row in rows]


def slot_is_available(start, duration, booked_ranges):
    end = start + timedelta(minutes=duration)
    return start > business_now() and is_opening_hours(start, end) and not any(
        start < booked_end and end > booked_start
        for booked_start, booked_end in booked_ranges
    )


@app.get('/api/availability')
def availability():
    barber = request.args.get('barbeiro', '').strip()
    selected_date = request.args.get('date', '').strip()
    service = request.args.get('servico', '').strip()
    duration = SERVICE_DURATIONS.get(service, 30)

    if barber not in {'Pedro Cristóvão', 'Oliveira'}:
        return jsonify({'error': 'Barbeiro inválido.'}), 400
    try:
        chosen_date = date.fromisoformat(selected_date)
    except ValueError:
        return jsonify({'error': 'Data inválida.'}), 400

    if chosen_date.weekday() >= 6:
        return jsonify({'duration': duration, 'slots': [], 'closed': True})

    booked_ranges = get_booked_ranges(barber, selected_date)
    slots = []
    for period_start, period_end in ((OPENING_TIME, MORNING_END), (AFTERNOON_START, CLOSING_TIME)):
        current = datetime.combine(chosen_date, period_start)
        last_start = min(
            datetime.combine(chosen_date, period_end) - timedelta(minutes=duration),
            datetime.combine(chosen_date, LAST_BOOKING_START),
        )
        while current <= last_start:
            slots.append({
                'value': current.strftime('%Y-%m-%dT%H:%M'),
                'label': current.strftime('%H:%M'),
                'available': slot_is_available(current, duration, booked_ranges),
            })
            current += timedelta(minutes=30)
    return jsonify({'duration': duration, 'slots': slots})


@app.post('/api/bookings')
def create_booking():
    payload = request.get_json(silent=True) or {}
    name = str(payload.get('nome', '')).strip()
    phone = str(payload.get('telemovel', '')).strip()
    service = str(payload.get('servico', '')).strip()
    barber = str(payload.get('barbeiro', '')).strip()
    raw_start = str(payload.get('data_hora', '')).strip()
    duration = SERVICE_DURATIONS.get(service)

    if not all([name, phone, service, barber, raw_start]) or not duration:
        return jsonify({'error': 'Preencha todos os dados do agendamento.'}), 400
    if barber not in {'Pedro Cristóvão', 'Oliveira'}:
        return jsonify({'error': 'Barbeiro inválido.'}), 400
    try:
        start = parse_booking_start(raw_start)
    except ValueError:
        return jsonify({'error': 'Horário inválido.'}), 400
    end = start + timedelta(minutes=duration)
    if start <= business_now() or start.minute not in {0, 30} or not is_opening_hours(start, end) or start.time() > LAST_BOOKING_START:
        return jsonify({'error': 'Esse horário está fora do horário de funcionamento.'}), 400

    # BEGIN IMMEDIATE serializa as confirmações concorrentes e impede duas reservas no mesmo horário.
    connection = get_db()
    try:
        connection.execute('BEGIN IMMEDIATE')
        conflict = connection.execute(
            """SELECT id FROM bookings
               WHERE barber = ? AND status != 'cancelled'
               AND starts_at < ? AND ends_at > ? LIMIT 1""",
            (barber, end.isoformat(timespec='minutes'), start.isoformat(timespec='minutes')),
        ).fetchone()
        if conflict:
            connection.rollback()
            return jsonify({'error': 'Este horário acabou de ser ocupado. Escolha outro.'}), 409

        cancel_token = secrets.token_urlsafe(32)
        cursor = connection.execute(
            """INSERT INTO bookings(name, phone, service, barber, starts_at, ends_at, cancel_token)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (name, phone, service, barber, start.isoformat(timespec='minutes'), end.isoformat(timespec='minutes'), cancel_token),
        )
        connection.commit()
        return jsonify({
            'booking_id': cursor.lastrowid,
            'starts_at': start.isoformat(timespec='minutes'),
            'admin_url': f"{PUBLIC_BASE_URL}/admin",
        }), 201
    finally:
        connection.close()


@app.route('/booking/cancel/<token>', methods=['GET', 'POST'])
def cancel_booking(token):
    with get_db() as connection:
        booking = connection.execute(
            "SELECT id, name, service, barber, starts_at, status FROM bookings WHERE cancel_token = ?",
            (token,),
        ).fetchone()
        if booking is None:
            return "<h1>Marcação não encontrada</h1><p>Esta ligação já não é válida.</p>", 404

        if request.method == 'POST' and booking['status'] != 'cancelled':
            connection.execute("UPDATE bookings SET status = 'cancelled' WHERE id = ?", (booking['id'],))
            connection.commit()
            booking = dict(booking)
            booking['status'] = 'cancelled'

    start_display = datetime.fromisoformat(booking['starts_at']).strftime('%d/%m/%Y às %H:%M')
    if booking['status'] == 'cancelled':
        return f"<main style='font-family:Arial;max-width:560px;margin:60px auto;padding:24px'><h1>Marcação cancelada</h1><p>O horário de {start_display} com {booking['barber']} voltou a ficar disponível.</p></main>"
    return f"""
    <main style='font-family:Arial;max-width:560px;margin:60px auto;padding:24px'>
      <h1>Cancelar marcação</h1>
      <p><strong>{booking['service']}</strong><br>{start_display}<br>Barbeiro: {booking['barber']}</p>
      <form method='post'><button style='background:#dc2626;color:#fff;border:0;border-radius:8px;padding:12px 18px;font-weight:bold'>Confirmar cancelamento</button></form>
    </main>
    """


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        password = request.form.get('password', '')
        if ADMIN_PASSWORD and secrets.compare_digest(password, ADMIN_PASSWORD):
            session.clear()
            session['admin_authenticated'] = True
            session.permanent = bool(request.form.get('remember'))
            return redirect(request.form.get('next') or url_for('admin_dashboard'))
        return render_template('admin_login.html', error='Password incorreta ou não configurada.', next=request.form.get('next', ''))
    return render_template('admin_login.html', error=None, next=request.args.get('next', ''))


@app.get('/admin/logout')
def admin_logout():
    session.clear()
    return redirect(url_for('admin_login'))


@app.get('/admin')
@admin_required
def admin_dashboard():
    selected_date = request.args.get('date', '').strip() or business_now().date().isoformat()
    try:
        date.fromisoformat(selected_date)
    except ValueError:
        selected_date = business_now().date().isoformat()

    with get_db() as connection:
        bookings = connection.execute(
            """SELECT id, name, phone, service, barber, starts_at, ends_at, status
               FROM bookings
               WHERE starts_at >= ? AND starts_at < ?
               ORDER BY starts_at ASC""",
            (f"{selected_date}T00:00", f"{selected_date}T23:59"),
        ).fetchall()
    return render_template('admin.html', bookings=bookings, selected_date=selected_date)


@app.post('/admin/bookings/<int:booking_id>/cancel')
@admin_required
def admin_cancel_booking(booking_id):
    with get_db() as connection:
        connection.execute(
            "UPDATE bookings SET status = 'cancelled' WHERE id = ? AND status != 'cancelled'",
            (booking_id,),
        )
        connection.commit()
    return redirect(url_for('admin_dashboard', date=request.form.get('date', '')))


init_db()

@app.route('/', methods=['GET', 'POST'])
def home():
    mensagem_sucesso = None
    
    if request.method == 'POST':
        nome = request.form.get('nome')
        telemovel = request.form.get('telemovel')
        servico = request.form.get('servico')
        barbeiro = request.form.get('barbeiro')
        data_hora = request.form.get('data_hora')
        
        try:
            resend.Emails.send({
                "from": "PointFino Barbershop <onboarding@resend.dev>",
                "to": [EMAIL_DESTINO],
                "subject": f"💈 Nova Reserva PointFino: {nome} - {servico}",
                "html": f"""
                <h2>Nova Reserva Recebida!</h2>
                <p><strong>Cliente:</strong> {nome}</p>
                <p><strong>Telemóvel:</strong> {telemovel}</p>
                <p><strong>Serviço:</strong> {servico}</p>
                <p><strong>Barbeiro Preferido:</strong> {barbeiro}</p>
                <p><strong>Data/Hora Solicitada:</strong> {data_hora}</p>
                """
            })
            mensagem_sucesso = f"Obrigado, {nome}! A tua reserva para {servico} foi enviada. Confirmamos em breve!"
        except Exception as e:
            print(f"Erro ao enviar reserva: {e}")
            mensagem_sucesso = f"Obrigado, {nome}! Recebemos a tua solicitação de agendamento."

    equipa = [
        {
            'nome': 'Pedro Cristóvão',
            'cargo': 'Fundador & Master Barber',
            'foto': '/static/pedro.jpg.png',
            'especialidade': 'Cortes Clássicos & Visagismo'
        },
        {
            'nome': 'Oliveira',
            'cargo': 'Barber Specialist',
            'foto': '/static/oliveira.jpg.png',
            'especialidade': 'Barboterapia & Fade de Precisão'
        }
    ]
    servicos = [
        {'categoria': 'Cortes', 'nome': 'Corte Clássico / Fade', 'preco': '12€', 'tempo': '30 min'},
        {'categoria': 'Cortes', 'nome': 'Corte de Máquina', 'preco': '10€', 'tempo': '20 min'},
        {'categoria': 'Cortes', 'nome': 'Corte & Sobrancelha', 'preco': '14€', 'tempo': '40 min'},
        {'categoria': 'Barba', 'nome': 'Barba Tradicional', 'preco': '8€', 'tempo': '20 min'},
        {'categoria': 'Barba', 'nome': 'Barboterapia Premium', 'preco': '12€', 'tempo': '30 min'},
        {'categoria': 'Combos', 'nome': 'Combo PointFino (Corte + Barba + Sobrancelha)', 'preco': '20€', 'tempo': '50 min'},
        {'categoria': 'Cuidados', 'nome': 'Pigmentação & Platinado', 'preco': 'Sob Consulta', 'tempo': '60 min'},
    ]

    return render_template('index.html', equipa=equipa, servicos=servicos, mensagem_sucesso=mensagem_sucesso)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
