import hashlib
import os
import secrets
import sqlite3
from datetime import datetime
from urllib.parse import urlencode

from flask import Flask, jsonify, redirect, render_template, request, session

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me-in-production")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

EMAIL_USER    = os.environ.get("EMAIL_USER", "")
EMAIL_PASS    = os.environ.get("EMAIL_PASS", "")
BASE_URL      = os.environ.get("BASE_URL", "http://localhost:5000")
DATABASE_PATH = os.environ.get("DATABASE_PATH", "banco.db")

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    nome         VARCHAR(100),
    email        VARCHAR(150) UNIQUE,
    senha_hash   VARCHAR(64),
    verificado   INTEGER DEFAULT 1,
    token_verif  VARCHAR(64),
    criado_em    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS clientes (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    nome     VARCHAR(100),
    segmento VARCHAR(50),
    email    VARCHAR(150)
);

CREATE TABLE IF NOT EXISTS metricas_meta (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id  INTEGER,
    data        DATE,
    cpm         DECIMAL(10,2),
    cpc         DECIMAL(10,2),
    ctr         DECIMAL(5,2),
    roas        DECIMAL(5,2),
    cpa         DECIMAL(10,2),
    frequencia  DECIMAL(5,2),
    conversoes  INTEGER
);

CREATE TABLE IF NOT EXISTS metricas_google (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id          INTEGER,
    data                DATE,
    impressoes          INTEGER,
    ctr                 DECIMAL(5,2),
    cpc                 DECIMAL(10,2),
    cpa                 DECIMAL(10,2),
    roas                DECIMAL(5,2),
    conversoes          INTEGER,
    parcela_impressao   DECIMAL(5,2)
);

CREATE TABLE IF NOT EXISTS metricas_reels (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id          INTEGER,
    data                DATE,
    nome_video          VARCHAR(100),
    views               VARCHAR(10),
    retencao            DECIMAL(5,2),
    alcance             INTEGER,
    curtidas            INTEGER,
    comentarios         INTEGER,
    compartilhamentos   INTEGER,
    salvamentos         INTEGER
);

CREATE TABLE IF NOT EXISTS metas (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id      INTEGER UNIQUE,
    roas_meta       DECIMAL(5,2),
    cpa_meta        DECIMAL(10,2),
    ctr_meta        DECIMAL(5,2),
    retencao_meta   DECIMAL(5,2)
);

CREATE TABLE IF NOT EXISTS ganchos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id  INTEGER,
    texto       TEXT,
    categoria   VARCHAR(50),
    retencao    DECIMAL(5,2),
    data_uso    DATE,
    criado_em   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS eventos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id      INTEGER,
    titulo          VARCHAR(200),
    tipo            VARCHAR(50),
    data_evento     DATE,
    hora            VARCHAR(10),
    descricao       TEXT,
    google_event_id VARCHAR(200),
    criado_em       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        for statement in SCHEMA.strip().split(";"):
            stmt = statement.strip()
            if stmt:
                conn.execute(stmt)
        conn.commit()


init_db()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def hash_senha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def is_logged_in() -> bool:
    return bool(session.get("logado"))


def send_email(to: str, subject: str, html: str, plain: str = "") -> bool:
    """Send an e-mail via Gmail SMTP SSL. Returns True on success."""
    if not EMAIL_USER or not EMAIL_PASS:
        app.logger.warning("EMAIL_USER ou EMAIL_PASS não configurados.")
        return False
    try:
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"Amigo Gestor <{EMAIL_USER}>"
        msg["To"]      = to
        if plain:
            msg.attach(MIMEText(plain, "plain", "utf-8"))
        msg.attach(MIMEText(html, "html", "utf-8"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_USER, EMAIL_PASS)
            server.sendmail(EMAIL_USER, to, msg.as_string())
        return True
    except Exception as exc:
        app.logger.error("Erro ao enviar e-mail: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Routes — setup & auth
# ---------------------------------------------------------------------------


@app.route("/setup", methods=["GET", "POST"])
def setup():
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]
    if total > 0:
        return redirect("/login")

    erro = None
    if request.method == "POST":
        nome    = request.form.get("nome", "").strip()
        email   = request.form.get("email", "").strip().lower()
        senha   = request.form.get("senha", "")
        confirm = request.form.get("senha_confirm", "")

        if not nome or not email or not senha:
            erro = "Preencha todos os campos."
        elif len(senha) < 6:
            erro = "Senha com ao menos 6 caracteres."
        elif senha != confirm:
            erro = "As senhas não coincidem."
        else:
            try:
                with get_conn() as conn:
                    conn.execute(
                        "INSERT INTO usuarios (nome, email, senha_hash, verificado) VALUES (?, ?, ?, 1)",
                        (nome, email, hash_senha(senha)),
                    )
                    conn.commit()
                return redirect("/login?setup=1")
            except sqlite3.IntegrityError:
                erro = "E-mail já cadastrado."

    return render_template("setup.html", erro=erro)


@app.route("/login", methods=["GET", "POST"])
def login():
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]
    if total == 0:
        return redirect("/setup")
    if is_logged_in():
        return redirect("/")

    erro  = None
    aviso = request.args.get("setup") or request.args.get("senha_redefinida") or request.args.get("cadastro")

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")
        with get_conn() as conn:
            user = conn.execute(
                "SELECT id, nome, senha_hash FROM usuarios WHERE email = ?", (email,)
            ).fetchone()
        if user and user["senha_hash"] == hash_senha(senha):
            session["logado"]       = True
            session["usuario_id"]   = user["id"]
            session["usuario_nome"] = user["nome"]
            return redirect("/")
        erro = "E-mail ou senha incorretos."

    return render_template("login.html", erro=erro, aviso=aviso)


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


@app.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    if is_logged_in():
        return redirect("/")

    erro = None
    if request.method == "POST":
        nome    = request.form.get("nome", "").strip()
        email   = request.form.get("email", "").strip().lower()
        senha   = request.form.get("senha", "")
        confirm = request.form.get("senha_confirm", "")

        if not nome or not email or not senha:
            erro = "Preencha todos os campos."
        elif len(senha) < 6:
            erro = "Senha com ao menos 6 caracteres."
        elif senha != confirm:
            erro = "As senhas não coincidem."
        else:
            try:
                with get_conn() as conn:
                    conn.execute(
                        "INSERT INTO usuarios (nome, email, senha_hash, verificado) VALUES (?, ?, ?, 1)",
                        (nome, email, hash_senha(senha)),
                    )
                    conn.commit()
                return redirect("/login?cadastro=1")
            except sqlite3.IntegrityError:
                erro = "Este e-mail já está cadastrado."

    return render_template("cadastro.html", erro=erro)


@app.route("/esqueci-senha", methods=["GET", "POST"])
def esqueci_senha():
    if is_logged_in():
        return redirect("/")

    resultado = None
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        with get_conn() as conn:
            user = conn.execute("SELECT id FROM usuarios WHERE email = ?", (email,)).fetchone()
            if user:
                token = secrets.token_urlsafe(32)
                conn.execute("UPDATE usuarios SET token_verif = ? WHERE id = ?", (token, user["id"]))
                conn.commit()
                link = f"{BASE_URL}/redefinir-senha/{token}"
                html = f"""
                <div style="font-family:Arial,sans-serif;max-width:500px;margin:auto;
                            background:#0f172a;color:#e2e8f0;padding:32px;border-radius:12px;">
                  <h2 style="color:#93c5fd;">Amigo Gestor</h2>
                  <p style="margin:16px 0;">Recebemos um pedido para redefinir sua senha.</p>
                  <a href="{link}" style="display:inline-block;padding:12px 28px;background:#1e3a5f;
                     color:#93c5fd;border-radius:8px;text-decoration:none;font-weight:700;">
                     Redefinir senha
                  </a>
                  <p style="font-size:12px;color:#475569;margin-top:20px;">Ou copie: {link}</p>
                </div>
                """
                ok = send_email(email, "Redefinir senha - Amigo Gestor", html)
                resultado = "Link enviado para seu e-mail!" if ok else None
                if not ok:
                    return redirect(f"/redefinir-senha/{token}")
            else:
                resultado = "Se este e-mail estiver cadastrado, o link será enviado."

    return render_template("esqueci_senha.html", resultado=resultado)


@app.route("/redefinir-senha/<token>", methods=["GET", "POST"])
def redefinir_senha(token: str):
    if is_logged_in():
        return redirect("/")

    with get_conn() as conn:
        user = conn.execute(
            "SELECT id, nome FROM usuarios WHERE token_verif = ?", (token,)
        ).fetchone()

    if not user:
        return render_template("login.html", erro="Link inválido ou já utilizado.", aviso=None)

    erro = None
    if request.method == "POST":
        senha   = request.form.get("senha", "")
        confirm = request.form.get("senha_confirm", "")
        if len(senha) < 6:
            erro = "Senha com ao menos 6 caracteres."
        elif senha != confirm:
            erro = "As senhas não coincidem."
        else:
            with get_conn() as conn:
                conn.execute(
                    "UPDATE usuarios SET senha_hash = ?, token_verif = NULL WHERE id = ?",
                    (hash_senha(senha), user["id"]),
                )
                conn.commit()
            return redirect("/login?senha_redefinida=1")

    return render_template("redefinir_senha.html", token=token, nome=user["nome"], erro=erro)


# ---------------------------------------------------------------------------
# Routes — static pages
# ---------------------------------------------------------------------------


@app.route("/ajuda")
def ajuda():
    if not is_logged_in():
        return redirect("/login")
    return render_template("ajuda.html")


# ---------------------------------------------------------------------------
# Routes — admin
# ---------------------------------------------------------------------------


@app.route("/admin/usuarios")
def admin_usuarios():
    if not is_logged_in():
        return redirect("/login")
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, nome, email, verificado, criado_em FROM usuarios ORDER BY criado_em DESC"
        ).fetchall()
    return jsonify(
        [
            {
                "id": u["id"],
                "nome": u["nome"],
                "email": u["email"],
                "verificado": bool(u["verificado"]),
                "criado_em": u["criado_em"],
            }
            for u in rows
        ]
    )


# ---------------------------------------------------------------------------
# Routes — clientes (dashboard)
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    if not is_logged_in():
        return redirect("/login")

    hoje = datetime.now().date()
    with get_conn() as conn:
        clientes = conn.execute("SELECT * FROM clientes ORDER BY nome").fetchall()
        alertas  = {}
        for c in clientes:
            cid   = c["id"]
            ultima = None
            for tabela in ("metricas_meta", "metricas_google", "metricas_reels"):
                row = conn.execute(
                    f"SELECT data FROM {tabela} WHERE cliente_id = ? ORDER BY data DESC LIMIT 1",
                    (cid,),
                ).fetchone()
                if row:
                    try:
                        d = datetime.strptime(row["data"], "%Y-%m-%d").date()
                        if ultima is None or d > ultima:
                            ultima = d
                    except Exception:
                        pass
            if ultima is None:
                alertas[cid] = "sem-dados"
            elif (hoje - ultima).days > 10:
                alertas[cid] = "atrasado"
            else:
                alertas[cid] = "ok"

    return render_template("index.html", clientes=clientes, alertas=alertas)


@app.route("/novo-cliente", methods=["GET", "POST"])
def novo_cliente():
    if not is_logged_in():
        return redirect("/login")
    if request.method == "POST":
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO clientes (nome, segmento, email) VALUES (?, ?, ?)",
                (
                    request.form["nome"],
                    request.form["segmento"],
                    request.form.get("email_cliente", "").strip().lower(),
                ),
            )
            conn.commit()
        return redirect("/")
    return render_template("novo_cliente.html")


@app.route("/excluir-cliente/<int:cliente_id>", methods=["POST"])
def excluir_cliente(cliente_id: int):
    if not is_logged_in():
        return redirect("/login")
    with get_conn() as conn:
        for tabela in ("metricas_meta", "metricas_google", "metricas_reels", "metas", "ganchos", "eventos"):
            conn.execute(f"DELETE FROM {tabela} WHERE cliente_id = ?", (cliente_id,))
        conn.execute("DELETE FROM clientes WHERE id = ?", (cliente_id,))
        conn.commit()
    return redirect("/")


@app.route("/cliente/<int:cliente_id>")
def cliente(cliente_id: int):
    if not is_logged_in():
        return redirect("/login")
    with get_conn() as conn:
        c       = conn.execute("SELECT * FROM clientes WHERE id = ?", (cliente_id,)).fetchone()
        meta    = conn.execute("SELECT * FROM metricas_meta   WHERE cliente_id = ? ORDER BY data DESC", (cliente_id,)).fetchall()
        google  = conn.execute("SELECT * FROM metricas_google WHERE cliente_id = ? ORDER BY data DESC", (cliente_id,)).fetchall()
        reels   = conn.execute("SELECT * FROM metricas_reels  WHERE cliente_id = ? ORDER BY data DESC", (cliente_id,)).fetchall()
        metas_r = conn.execute("SELECT * FROM metas WHERE cliente_id = ?", (cliente_id,)).fetchone()
    return render_template("cliente.html", cliente=c, meta=meta, google=google, reels=reels, metas=metas_r)


# ---------------------------------------------------------------------------
# Routes — inserir / editar / excluir métricas
# ---------------------------------------------------------------------------


@app.route("/inserir/<int:cliente_id>", methods=["GET", "POST"])
def inserir(cliente_id: int):
    if not is_logged_in():
        return redirect("/login")
    if request.method == "POST":
        canal = request.form["canal"]
        data  = request.form["data"]
        with get_conn() as conn:
            if canal == "meta":
                conn.execute(
                    """INSERT INTO metricas_meta
                       (cliente_id, data, cpm, cpc, ctr, roas, cpa, frequencia, conversoes)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        cliente_id, data,
                        request.form["cpm"],     request.form["cpc"],
                        request.form["ctr"],     request.form["roas"],
                        request.form["cpa"],     request.form["frequencia"],
                        request.form["conversoes"],
                    ),
                )
            elif canal == "google":
                conn.execute(
                    """INSERT INTO metricas_google
                       (cliente_id, data, impressoes, ctr, cpc, cpa, roas, conversoes, parcela_impressao)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        cliente_id, data,
                        request.form["impressoes"],        request.form["ctr"],
                        request.form["cpc"],               request.form["cpa"],
                        request.form["roas"],              request.form["conversoes"],
                        request.form["parcela_impressao"],
                    ),
                )
            elif canal == "reels":
                conn.execute(
                    """INSERT INTO metricas_reels
                       (cliente_id, data, nome_video, views, retencao, alcance,
                        curtidas, comentarios, compartilhamentos, salvamentos)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        cliente_id, data,
                        request.form["nome_video"],        request.form["views"],
                        request.form["retencao"],          request.form["alcance"],
                        request.form["curtidas"],          request.form["comentarios"],
                        request.form["compartilhamentos"], request.form["salvamentos"],
                    ),
                )
            conn.commit()
        return redirect(f"/cliente/{cliente_id}")
    return render_template("inserir.html", id=cliente_id)


def _excluir_metrica(tabela: str, registro_id: int):
    """Remove uma linha de qualquer tabela de métricas e retorna o cliente_id."""
    with get_conn() as conn:
        row = conn.execute(f"SELECT cliente_id FROM {tabela} WHERE id = ?", (registro_id,)).fetchone()
        conn.execute(f"DELETE FROM {tabela} WHERE id = ?", (registro_id,))
        conn.commit()
    return row["cliente_id"] if row else None


@app.route("/excluir/meta/<int:registro_id>",   methods=["POST"])
def excluir_meta(registro_id: int):
    if not is_logged_in(): return redirect("/login")
    cid = _excluir_metrica("metricas_meta", registro_id)
    return redirect(f"/cliente/{cid}" if cid else "/")

@app.route("/excluir/google/<int:registro_id>", methods=["POST"])
def excluir_google(registro_id: int):
    if not is_logged_in(): return redirect("/login")
    cid = _excluir_metrica("metricas_google", registro_id)
    return redirect(f"/cliente/{cid}" if cid else "/")

@app.route("/excluir/reels/<int:registro_id>",  methods=["POST"])
def excluir_reels(registro_id: int):
    if not is_logged_in(): return redirect("/login")
    cid = _excluir_metrica("metricas_reels", registro_id)
    return redirect(f"/cliente/{cid}" if cid else "/")


@app.route("/editar/meta/<int:registro_id>", methods=["GET", "POST"])
def editar_meta(registro_id: int):
    if not is_logged_in(): return redirect("/login")
    with get_conn() as conn:
        if request.method == "POST":
            conn.execute(
                """UPDATE metricas_meta
                   SET data=?, cpm=?, cpc=?, ctr=?, roas=?, cpa=?, frequencia=?, conversoes=?
                   WHERE id=?""",
                (
                    request.form["data"],     request.form["cpm"],
                    request.form["cpc"],      request.form["ctr"],
                    request.form["roas"],     request.form["cpa"],
                    request.form["frequencia"], request.form["conversoes"],
                    registro_id,
                ),
            )
            conn.commit()
            row = conn.execute("SELECT cliente_id FROM metricas_meta WHERE id=?", (registro_id,)).fetchone()
            return redirect(f"/cliente/{row['cliente_id']}")
        m = conn.execute("SELECT * FROM metricas_meta WHERE id=?", (registro_id,)).fetchone()
    return render_template("editar_meta.html", m=m)


@app.route("/editar/google/<int:registro_id>", methods=["GET", "POST"])
def editar_google(registro_id: int):
    if not is_logged_in(): return redirect("/login")
    with get_conn() as conn:
        if request.method == "POST":
            conn.execute(
                """UPDATE metricas_google
                   SET data=?, impressoes=?, ctr=?, cpc=?, cpa=?, roas=?, conversoes=?, parcela_impressao=?
                   WHERE id=?""",
                (
                    request.form["data"],          request.form["impressoes"],
                    request.form["ctr"],           request.form["cpc"],
                    request.form["cpa"],           request.form["roas"],
                    request.form["conversoes"],    request.form["parcela_impressao"],
                    registro_id,
                ),
            )
            conn.commit()
            row = conn.execute("SELECT cliente_id FROM metricas_google WHERE id=?", (registro_id,)).fetchone()
            return redirect(f"/cliente/{row['cliente_id']}")
        m = conn.execute("SELECT * FROM metricas_google WHERE id=?", (registro_id,)).fetchone()
    return render_template("editar_google.html", m=m)


@app.route("/editar/reels/<int:registro_id>", methods=["GET", "POST"])
def editar_reels(registro_id: int):
    if not is_logged_in(): return redirect("/login")
    with get_conn() as conn:
        if request.method == "POST":
            conn.execute(
                """UPDATE metricas_reels
                   SET data=?, nome_video=?, views=?, retencao=?, alcance=?,
                       curtidas=?, comentarios=?, compartilhamentos=?, salvamentos=?
                   WHERE id=?""",
                (
                    request.form["data"],               request.form["nome_video"],
                    request.form["views"],              request.form["retencao"],
                    request.form["alcance"],            request.form["curtidas"],
                    request.form["comentarios"],        request.form["compartilhamentos"],
                    request.form["salvamentos"],        registro_id,
                ),
            )
            conn.commit()
            row = conn.execute("SELECT cliente_id FROM metricas_reels WHERE id=?", (registro_id,)).fetchone()
            return redirect(f"/cliente/{row['cliente_id']}")
        m = conn.execute("SELECT * FROM metricas_reels WHERE id=?", (registro_id,)).fetchone()
    return render_template("editar_reels.html", m=m)


# ---------------------------------------------------------------------------
# Routes — review semanal
# ---------------------------------------------------------------------------


@app.route("/review/<int:cliente_id>")
def review(cliente_id: int):
    if not is_logged_in():
        return redirect("/login")

    with get_conn() as conn:
        c = conn.execute("SELECT * FROM clientes WHERE id=?", (cliente_id,)).fetchone()
        semanas = [
            r[0]
            for r in conn.execute(
                """SELECT DISTINCT data FROM (
                    SELECT data FROM metricas_meta    WHERE cliente_id=?
                    UNION
                    SELECT data FROM metricas_google  WHERE cliente_id=?
                    UNION
                    SELECT data FROM metricas_reels   WHERE cliente_id=?
                ) ORDER BY data DESC""",
                (cliente_id, cliente_id, cliente_id),
            ).fetchall()
        ]

        semana_atual = request.args.get("semana", semanas[0] if semanas else None)
        meta_semana = google_semana = meta_ant = google_ant = None
        reels_semana = reels_ant = []

        if semana_atual and semanas:
            idx     = semanas.index(semana_atual) if semana_atual in semanas else 0
            sem_ant = semanas[idx + 1] if idx + 1 < len(semanas) else None

            meta_semana   = conn.execute("SELECT * FROM metricas_meta   WHERE cliente_id=? AND data=?", (cliente_id, semana_atual)).fetchone()
            google_semana = conn.execute("SELECT * FROM metricas_google WHERE cliente_id=? AND data=?", (cliente_id, semana_atual)).fetchone()
            reels_semana  = conn.execute("SELECT * FROM metricas_reels  WHERE cliente_id=? AND data=?", (cliente_id, semana_atual)).fetchall()

            if sem_ant:
                meta_ant   = conn.execute("SELECT * FROM metricas_meta   WHERE cliente_id=? AND data=?", (cliente_id, sem_ant)).fetchone()
                google_ant = conn.execute("SELECT * FROM metricas_google WHERE cliente_id=? AND data=?", (cliente_id, sem_ant)).fetchone()
                reels_ant  = conn.execute("SELECT * FROM metricas_reels  WHERE cliente_id=? AND data=?", (cliente_id, sem_ant)).fetchall()

        meta   = conn.execute("SELECT * FROM metricas_meta   WHERE cliente_id=? ORDER BY data DESC", (cliente_id,)).fetchall()
        google = conn.execute("SELECT * FROM metricas_google WHERE cliente_id=? ORDER BY data DESC", (cliente_id,)).fetchall()
        reels  = conn.execute("SELECT * FROM metricas_reels  WHERE cliente_id=? ORDER BY data DESC", (cliente_id,)).fetchall()

    # --- health score ---
    alertas = 0
    if meta_semana:
        cpa = float(meta_semana["cpa"] or 0)
        alertas += 2 if cpa < 1.5 else (1 if cpa < 3 else 0)
        alertas += 1 if float(meta_semana["roas"] or 0) > 3.5 else 0
    if google_semana:
        cpa_g = float(google_semana["cpa"] or 0)
        alertas += 2 if cpa_g < 2 else (1 if cpa_g < 4 else 0)
    if reels_semana:
        alertas += 2 if float(reels_semana[0]["retencao"] or 0) < 25 else (
            1 if float(reels_semana[0]["retencao"] or 0) < 40 else 0
        )

    if not meta_semana and not google_semana and not reels_semana:
        status_classe, status_texto = "status-neutro", "Sem dados"
    elif alertas >= 3:
        status_classe, status_texto = "status-critico", "Crítico"
    elif alertas >= 1:
        status_classe, status_texto = "status-atencao", "Atenção"
    else:
        status_classe, status_texto = "status-saudavel", "Saudável"

    dados_ia = {}
    if meta_semana:
        dados_ia["meta"] = {k: meta_semana[k] for k in ("cpm", "cpc", "ctr", "roas", "cpa", "frequencia", "conversoes")}
    if google_semana:
        dados_ia["google"] = {k: google_semana[k] for k in ("impressoes", "ctr", "cpc", "cpa", "roas", "conversoes", "parcela_impressao")}
    if reels_semana:
        dados_ia["reels"] = [
            {k: r[k] for k in ("nome_video", "views", "retencao", "alcance", "curtidas", "comentarios", "compartilhamentos", "salvamentos")}
            for r in reels_semana
        ]

    return render_template(
        "review.html",
        cliente=c,
        semanas=semanas,
        semana_atual=semana_atual,
        meta_semana=meta_semana,
        google_semana=google_semana,
        reels_semana=reels_semana,
        meta_ant=meta_ant,
        google_ant=google_ant,
        reels_ant=reels_ant,
        meta=meta,
        google=google,
        reels=reels,
        historico_meta=list(reversed(meta)),
        historico_google=list(reversed(google)),
        historico_reels=list(reversed(reels)),
        status_classe=status_classe,
        status_texto=status_texto,
        dados_ia=dados_ia,
    )


# ---------------------------------------------------------------------------
# Routes — relatório BI
# ---------------------------------------------------------------------------


@app.route("/relatorio/<int:cliente_id>")
def relatorio(cliente_id: int):
    if not is_logged_in():
        return redirect("/login")

    with get_conn() as conn:
        c = conn.execute("SELECT * FROM clientes WHERE id=?", (cliente_id,)).fetchone()
        tipo_periodo  = request.args.get("tipo", "semanal")
        semanas = [
            r[0]
            for r in conn.execute(
                """SELECT DISTINCT data FROM (
                    SELECT data FROM metricas_meta    WHERE cliente_id=?
                    UNION
                    SELECT data FROM metricas_google  WHERE cliente_id=?
                    UNION
                    SELECT data FROM metricas_reels   WHERE cliente_id=?
                ) ORDER BY data DESC""",
                (cliente_id, cliente_id, cliente_id),
            ).fetchall()
        ]
        periodo_atual = request.args.get("periodo", semanas[0] if semanas else None)

        if tipo_periodo == "mensal" and periodo_atual:
            semanas_do_periodo = [s for s in semanas if s.startswith(periodo_atual[:7])]
        else:
            semanas_do_periodo = [periodo_atual] if periodo_atual else []

        meta_periodo = google_periodo = reels_periodo = []
        if semanas_do_periodo:
            ph = ",".join(["?"] * len(semanas_do_periodo))
            meta_periodo   = conn.execute(f"SELECT * FROM metricas_meta   WHERE cliente_id=? AND data IN ({ph}) ORDER BY data", [cliente_id] + semanas_do_periodo).fetchall()
            google_periodo = conn.execute(f"SELECT * FROM metricas_google WHERE cliente_id=? AND data IN ({ph}) ORDER BY data", [cliente_id] + semanas_do_periodo).fetchall()
            reels_periodo  = conn.execute(f"SELECT * FROM metricas_reels  WHERE cliente_id=? AND data IN ({ph}) ORDER BY data", [cliente_id] + semanas_do_periodo).fetchall()

        historico_meta   = conn.execute("SELECT * FROM metricas_meta   WHERE cliente_id=? ORDER BY data", (cliente_id,)).fetchall()
        historico_google = conn.execute("SELECT * FROM metricas_google WHERE cliente_id=? ORDER BY data", (cliente_id,)).fetchall()
        historico_reels  = conn.execute("SELECT * FROM metricas_reels  WHERE cliente_id=? ORDER BY data", (cliente_id,)).fetchall()

    conv_meta    = sum(int(m["conversoes"] or 0) for m in meta_periodo)
    conv_google  = sum(int(g["conversoes"] or 0) for g in google_periodo)
    roas_meta    = max((float(m["roas"] or 0) for m in meta_periodo),   default=0)
    roas_google  = max((float(g["roas"] or 0) for g in google_periodo), default=0)
    reels_validos = [r for r in reels_periodo if float(r["retencao"] or 0) <= 100]
    media_ret    = round(sum(float(r["retencao"] or 0) for r in reels_validos) / max(len(reels_validos), 1), 1) if reels_periodo else 0

    kpis = {
        "conversoes_total":  conv_meta + conv_google,
        "melhor_roas":       round(max(roas_meta, roas_google), 2),
        "melhor_roas_canal": "Meta Ads" if roas_meta >= roas_google else "Google Ads",
        "media_retencao":    media_ret,
        "total_reels":       len(reels_periodo),
        "canais_ativos":     sum([bool(meta_periodo), bool(google_periodo), bool(reels_periodo)]),
    }

    return render_template(
        "relatorio.html",
        cliente=c,
        semanas=semanas,
        periodo_atual=periodo_atual,
        tipo_periodo=tipo_periodo,
        meta_periodo=meta_periodo,
        google_periodo=google_periodo,
        reels_periodo=reels_periodo,
        historico_meta=historico_meta,
        historico_google=historico_google,
        historico_reels=historico_reels,
        kpis=kpis,
    )


# ---------------------------------------------------------------------------
# Routes — metas
# ---------------------------------------------------------------------------


@app.route("/metas/<int:cliente_id>", methods=["GET", "POST"])
def metas(cliente_id: int):
    if not is_logged_in():
        return redirect("/login")
    with get_conn() as conn:
        c = conn.execute("SELECT * FROM clientes WHERE id=?", (cliente_id,)).fetchone()
        if request.method == "POST":
            conn.execute(
                """INSERT INTO metas (cliente_id, roas_meta, cpa_meta, ctr_meta, retencao_meta)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(cliente_id) DO UPDATE SET
                       roas_meta     = excluded.roas_meta,
                       cpa_meta      = excluded.cpa_meta,
                       ctr_meta      = excluded.ctr_meta,
                       retencao_meta = excluded.retencao_meta""",
                (
                    cliente_id,
                    request.form.get("roas_meta")     or None,
                    request.form.get("cpa_meta")      or None,
                    request.form.get("ctr_meta")      or None,
                    request.form.get("retencao_meta") or None,
                ),
            )
            conn.commit()
            return redirect(f"/cliente/{cliente_id}")
        meta = conn.execute("SELECT * FROM metas WHERE cliente_id=?", (cliente_id,)).fetchone()
    return render_template("metas.html", cliente=c, meta=meta)


# ---------------------------------------------------------------------------
# Routes — ganchos
# ---------------------------------------------------------------------------


@app.route("/ganchos/<int:cliente_id>")
def ganchos(cliente_id: int):
    if not is_logged_in():
        return redirect("/login")
    with get_conn() as conn:
        c            = conn.execute("SELECT * FROM clientes WHERE id=?", (cliente_id,)).fetchone()
        ganchos_list = conn.execute("SELECT * FROM ganchos WHERE cliente_id=? ORDER BY criado_em DESC", (cliente_id,)).fetchall()
    return render_template("ganchos.html", cliente=c, ganchos=ganchos_list)


@app.route("/ganchos/<int:cliente_id>/novo", methods=["POST"])
def novo_gancho(cliente_id: int):
    if not is_logged_in():
        return redirect("/login")
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO ganchos (cliente_id, texto, categoria, retencao, data_uso) VALUES (?, ?, ?, ?, ?)",
            (
                cliente_id,
                request.form["texto"],
                request.form.get("categoria", "Geral"),
                request.form.get("retencao") or None,
                request.form.get("data_uso") or None,
            ),
        )
        conn.commit()
    return redirect(f"/ganchos/{cliente_id}")


@app.route("/ganchos/excluir/<int:gancho_id>", methods=["POST"])
def excluir_gancho(gancho_id: int):
    if not is_logged_in():
        return redirect("/login")
    with get_conn() as conn:
        row = conn.execute("SELECT cliente_id FROM ganchos WHERE id=?", (gancho_id,)).fetchone()
        conn.execute("DELETE FROM ganchos WHERE id=?", (gancho_id,))
        conn.commit()
    return redirect(f"/ganchos/{row['cliente_id']}" if row else "/")


# ---------------------------------------------------------------------------
# Routes — calendário
# ---------------------------------------------------------------------------

CORES_EVENTOS = {
    "postagem":  "#ec4899",
    "review":    "#3b82f6",
    "metricas":  "#f59e0b",
    "campanha":  "#22c55e",
    "reuniao":   "#a78bfa",
    "outro":     "#64748b",
}


@app.route("/calendario/<int:cliente_id>")
def calendario(cliente_id: int):
    if not is_logged_in():
        return redirect("/login")
    with get_conn() as conn:
        c              = conn.execute("SELECT * FROM clientes WHERE id=?", (cliente_id,)).fetchone()
        eventos_list   = conn.execute("SELECT * FROM eventos WHERE cliente_id=? ORDER BY data_evento", (cliente_id,)).fetchall()
        todos_clientes = conn.execute("SELECT id, nome FROM clientes ORDER BY nome").fetchall()
    return render_template("calendario.html", cliente=c, eventos=eventos_list, todos_clientes=todos_clientes)


@app.route("/calendario/<int:cliente_id>/novo", methods=["POST"])
def novo_evento(cliente_id: int):
    if not is_logged_in():
        return redirect("/login")

    titulo      = request.form["titulo"]
    tipo        = request.form["tipo"]
    data_evento = request.form["data_evento"]
    hora        = request.form.get("hora", "")
    descricao   = request.form.get("descricao", "")
    email_conv  = request.form.get("email_convite", "").strip().lower()

    with get_conn() as conn:
        conn.execute(
            "INSERT INTO eventos (cliente_id, titulo, tipo, data_evento, hora, descricao) VALUES (?, ?, ?, ?, ?, ?)",
            (cliente_id, titulo, tipo, data_evento, hora, descricao),
        )
        conn.commit()

    if email_conv and tipo == "reuniao":
        try:
            data_fmt = datetime.strptime(data_evento, "%Y-%m-%d").strftime("%d/%m/%Y")
        except Exception:
            data_fmt = data_evento

        hora_fmt = hora if hora else "Horário a definir"
        dt       = data_evento.replace("-", "")

        if hora:
            h_ini      = hora.replace(":", "") + "00"
            hora_parts = hora.split(":")
            h_end      = str(int(hora_parts[0]) + 1).zfill(2) + hora_parts[1] + "00"
            gcal_dates = f"{dt}T{h_ini}/{dt}T{h_end}"
        else:
            gcal_dates = f"{dt}/{dt}"

        gcal_link = "https://calendar.google.com/calendar/render?" + urlencode(
            {
                "action":  "TEMPLATE",
                "text":    titulo,
                "dates":   gcal_dates,
                "details": (descricao or "") + "\n\nAgendado pelo Amigo Gestor",
            }
        )

        html_email = f"""
        <div style="font-family:Arial,sans-serif;max-width:520px;margin:auto;
                    background:#0f172a;color:#e2e8f0;padding:32px;border-radius:12px;">
          <h2 style="color:#93c5fd;">Convite de Reunião</h2>
          <div style="background:#0a0f1e;border-radius:10px;padding:20px;margin:20px 0;">
            <p style="font-size:18px;font-weight:700;margin-bottom:12px;">{titulo}</p>
            <p style="color:#94a3b8;margin:6px 0;">Data: <strong style="color:#e2e8f0;">{data_fmt}</strong></p>
            <p style="color:#94a3b8;margin:6px 0;">Horário: <strong style="color:#e2e8f0;">{hora_fmt}</strong></p>
            {"<p style='color:#94a3b8;margin-top:12px;'>" + descricao + "</p>" if descricao else ""}
          </div>
          <a href="{gcal_link}" style="display:inline-block;padding:12px 24px;background:#1e3a5f;
             color:#93c5fd;border-radius:8px;text-decoration:none;font-weight:700;">
             Adicionar ao Google Calendar
          </a>
        </div>
        """
        send_email(email_conv, f"Reunião: {titulo} - {data_fmt}", html_email)

    return redirect(f"/calendario/{cliente_id}")


@app.route("/calendario/excluir/<int:evento_id>", methods=["POST"])
def excluir_evento(evento_id: int):
    if not is_logged_in():
        return redirect("/login")
    with get_conn() as conn:
        row = conn.execute("SELECT cliente_id FROM eventos WHERE id=?", (evento_id,)).fetchone()
        conn.execute("DELETE FROM eventos WHERE id=?", (evento_id,))
        conn.commit()
    return redirect(f"/calendario/{row['cliente_id']}" if row else "/")


@app.route("/api/eventos/<int:cliente_id>")
def api_eventos(cliente_id: int):
    if not is_logged_in():
        return jsonify([])
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM eventos WHERE cliente_id=? ORDER BY data_evento", (cliente_id,)
        ).fetchall()
    return jsonify(
        [
            {
                "id":              r["id"],
                "title":           r["titulo"],
                "start":           r["data_evento"] + (f"T{r['hora']}" if r["hora"] else ""),
                "backgroundColor": CORES_EVENTOS.get(r["tipo"], "#64748b"),
                "borderColor":     CORES_EVENTOS.get(r["tipo"], "#64748b"),
                "extendedProps":   {"tipo": r["tipo"], "descricao": r["descricao"] or ""},
            }
            for r in rows
        ]
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(debug=debug)
