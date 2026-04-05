from flask import Flask, render_template, request, redirect, session, jsonify
import sqlite3, hashlib, os, secrets
from datetime import datetime
from urllib.parse import urlencode

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'amigogestor2026secret')

EMAIL_USER = os.environ.get('EMAIL_USER', '')
EMAIL_PASS = os.environ.get('EMAIL_PASS', '')
BASE_URL   = os.environ.get('BASE_URL', 'http://localhost:5000')


# ─── BANCO ────────────────────────────────────────────────────────────
def criar_banco():
    conn = sqlite3.connect('banco.db')
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS usuarios (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        nome       VARCHAR(100),
        email      VARCHAR(150) UNIQUE,
        senha_hash VARCHAR(64),
        verificado INTEGER DEFAULT 1,
        token_verif VARCHAR(64),
        criado_em  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    for col, defn in [('verificado','INTEGER DEFAULT 1'),('token_verif','VARCHAR(64)')]:
        try: c.execute(f'ALTER TABLE usuarios ADD COLUMN {col} {defn}')
        except Exception: pass

    c.execute('''CREATE TABLE IF NOT EXISTS clientes (
        id INTEGER PRIMARY KEY AUTOINCREMENT, nome VARCHAR(100),
        segmento VARCHAR(50), email VARCHAR(150)
    )''')
    try: c.execute('ALTER TABLE clientes ADD COLUMN email VARCHAR(150)')
    except Exception: pass

    c.execute('''CREATE TABLE IF NOT EXISTS metricas_meta (
        id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER, data DATE,
        cpm DECIMAL(10,2), cpc DECIMAL(10,2), ctr DECIMAL(5,2),
        roas DECIMAL(5,2), cpa DECIMAL(10,2), frequencia DECIMAL(5,2), conversoes INTEGER
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS metricas_google (
        id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER, data DATE,
        impressoes INTEGER, ctr DECIMAL(5,2), cpc DECIMAL(10,2), cpa DECIMAL(10,2),
        roas DECIMAL(5,2), conversoes INTEGER, parcela_impressao DECIMAL(5,2)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS metricas_reels (
        id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER, data DATE,
        nome_video VARCHAR(100), views VARCHAR(10), retencao DECIMAL(5,2),
        alcance INTEGER, curtidas INTEGER, comentarios INTEGER,
        compartilhamentos INTEGER, salvamentos INTEGER
    )''')
    try: c.execute('ALTER TABLE metricas_reels ADD COLUMN nome_video VARCHAR(100)')
    except Exception: pass

    c.execute('''CREATE TABLE IF NOT EXISTS metas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER UNIQUE,
        roas_meta DECIMAL(5,2), cpa_meta DECIMAL(10,2),
        ctr_meta DECIMAL(5,2), retencao_meta DECIMAL(5,2)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS ganchos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER,
        texto TEXT, categoria VARCHAR(50), retencao DECIMAL(5,2),
        data_uso DATE, criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS eventos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER,
        titulo VARCHAR(200), tipo VARCHAR(50), data_evento DATE,
        hora VARCHAR(10), descricao TEXT, google_event_id VARCHAR(200),
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    conn.commit()
    conn.close()

criar_banco()


def hash_senha(s): return hashlib.sha256(s.encode()).hexdigest()
def logado(): return session.get('logado')

def enviar_email(para, assunto, html, txt=''):
    if not EMAIL_USER or not EMAIL_PASS:
        app.logger.warning('EMAIL_USER ou EMAIL_PASS nao configurados.')
        return False
    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        msg = MIMEMultipart('alternative')
        msg['Subject'] = assunto
        msg['From']    = f'Amigo Gestor <{EMAIL_USER}>'
        msg['To']      = para
        if txt: msg.attach(MIMEText(txt, 'plain', 'utf-8'))
        msg.attach(MIMEText(html, 'html', 'utf-8'))
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
            s.login(EMAIL_USER, EMAIL_PASS)
            s.sendmail(EMAIL_USER, para, msg.as_string())
        return True
    except Exception as e:
        app.logger.error(f'Erro email: {e}'); return False


# ─── SETUP ────────────────────────────────────────────────────────────
@app.route('/setup', methods=['GET', 'POST'])
def setup():
    conn  = sqlite3.connect('banco.db')
    total = conn.execute('SELECT COUNT(*) FROM usuarios').fetchone()[0]
    conn.close()
    if total > 0: return redirect('/login')
    erro = None
    if request.method == 'POST':
        nome=request.form.get('nome','').strip(); email=request.form.get('email','').strip().lower()
        senha=request.form.get('senha',''); confirm=request.form.get('senha_confirm','')
        if not nome or not email or not senha: erro='Preencha todos os campos.'
        elif len(senha)<6: erro='Senha com ao menos 6 caracteres.'
        elif senha!=confirm: erro='As senhas nao coincidem.'
        else:
            try:
                conn=sqlite3.connect('banco.db')
                conn.execute('INSERT INTO usuarios (nome,email,senha_hash,verificado) VALUES (?,?,?,1)',
                    (nome,email,hash_senha(senha)))
                conn.commit(); conn.close()
                return redirect('/login?setup=1')
            except sqlite3.IntegrityError: erro='E-mail ja cadastrado.'
    return render_template('setup.html', erro=erro)


# ─── LOGIN / LOGOUT ───────────────────────────────────────────────────
@app.route('/login', methods=['GET', 'POST'])
def login():
    conn  = sqlite3.connect('banco.db')
    total = conn.execute('SELECT COUNT(*) FROM usuarios').fetchone()[0]
    conn.close()
    if total == 0: return redirect('/setup')
    if logado(): return redirect('/')
    erro  = None
    aviso = request.args.get('setup') or request.args.get('senha_redefinida') or request.args.get('cadastro')
    if request.method == 'POST':
        email=request.form.get('email','').strip().lower()
        senha=request.form.get('senha','')
        conn=sqlite3.connect('banco.db')
        u=conn.execute('SELECT id,nome,senha_hash FROM usuarios WHERE email=?',(email,)).fetchone()
        conn.close()
        if u and u[2]==hash_senha(senha):
            session['logado']=True; session['usuario_id']=u[0]; session['usuario_nome']=u[1]
            return redirect('/')
        else: erro='E-mail ou senha incorretos.'
    return render_template('login.html', erro=erro, aviso=aviso)

@app.route('/logout')
def logout(): session.clear(); return redirect('/login')


# ─── CADASTRO ─────────────────────────────────────────────────────────
@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    if logado(): return redirect('/')
    erro=sucesso=None
    if request.method=='POST':
        nome=request.form.get('nome','').strip(); email=request.form.get('email','').strip().lower()
        senha=request.form.get('senha',''); confirm=request.form.get('senha_confirm','')
        if not nome or not email or not senha: erro='Preencha todos os campos.'
        elif len(senha)<6: erro='Senha com ao menos 6 caracteres.'
        elif senha!=confirm: erro='As senhas nao coincidem.'
        else:
            try:
                conn=sqlite3.connect('banco.db')
                conn.execute('INSERT INTO usuarios (nome,email,senha_hash,verificado) VALUES (?,?,?,1)',
                    (nome,email,hash_senha(senha)))
                conn.commit(); conn.close()
                return redirect('/login?cadastro=1')
            except sqlite3.IntegrityError: erro='Este e-mail ja esta cadastrado.'
    return render_template('cadastro.html', erro=erro, sucesso=sucesso)


# ─── ESQUECI / REDEFINIR SENHA ────────────────────────────────────────
@app.route('/esqueci-senha', methods=['GET', 'POST'])
def esqueci_senha():
    if logado(): return redirect('/')
    resultado=None
    if request.method=='POST':
        email=request.form.get('email','').strip().lower()
        conn=sqlite3.connect('banco.db')
        u=conn.execute('SELECT id FROM usuarios WHERE email=?',(email,)).fetchone()
        if u:
            token=secrets.token_urlsafe(32)
            conn.execute('UPDATE usuarios SET token_verif=? WHERE id=?',(token,u[0]))
            conn.commit(); conn.close()
            link=f'{BASE_URL}/redefinir-senha/{token}'
            html=f'''<div style="font-family:Arial,sans-serif;max-width:500px;margin:auto;
                background:#0f172a;color:#e2e8f0;padding:32px;border-radius:12px;">
              <h2 style="color:#93c5fd;">Amigo Gestor</h2>
              <p style="margin:16px 0;">Recebemos um pedido para redefinir sua senha.</p>
              <a href="{link}" style="display:inline-block;padding:12px 28px;background:#1e3a5f;
                color:#93c5fd;border-radius:8px;text-decoration:none;font-weight:700;">Redefinir senha</a>
              <p style="font-size:12px;color:#475569;margin-top:20px;">Ou copie: {link}</p>
            </div>'''
            ok=enviar_email(email,'Redefinir senha - Amigo Gestor',html)
            if ok: resultado='Link enviado para seu e-mail!'
            else: return redirect(f'/redefinir-senha/{token}')
        else:
            conn.close()
            resultado='Se este e-mail estiver cadastrado, o link sera enviado.'
    return render_template('esqueci_senha.html', resultado=resultado)

@app.route('/redefinir-senha/<token>', methods=['GET', 'POST'])
def redefinir_senha(token):
    if logado(): return redirect('/')
    conn=sqlite3.connect('banco.db')
    u=conn.execute('SELECT id,nome FROM usuarios WHERE token_verif=?',(token,)).fetchone()
    conn.close()
    if not u: return render_template('login.html',erro='Link invalido ou ja utilizado.',aviso=None)
    erro=None
    if request.method=='POST':
        senha=request.form.get('senha',''); confirm=request.form.get('senha_confirm','')
        if len(senha)<6: erro='Senha com ao menos 6 caracteres.'
        elif senha!=confirm: erro='As senhas nao coincidem.'
        else:
            conn=sqlite3.connect('banco.db')
            conn.execute('UPDATE usuarios SET senha_hash=?,token_verif=NULL WHERE id=?',(hash_senha(senha),u[0]))
            conn.commit(); conn.close()
            return redirect('/login?senha_redefinida=1')
    return render_template('redefinir_senha.html', token=token, nome=u[1], erro=erro)


# ─── AJUDA ────────────────────────────────────────────────────────────
@app.route('/ajuda')
def ajuda():
    if not logado(): return redirect('/login')
    return render_template('ajuda.html')


# ─── ADMIN ────────────────────────────────────────────────────────────
@app.route('/admin/usuarios')
def admin_usuarios():
    if not logado(): return redirect('/login')
    conn=sqlite3.connect('banco.db')
    rows=conn.execute('SELECT id,nome,email,verificado,criado_em FROM usuarios ORDER BY criado_em DESC').fetchall()
    conn.close()
    return jsonify([{'id':u[0],'nome':u[1],'email':u[2],'verificado':bool(u[3]),'criado_em':u[4]} for u in rows])


# ─── INDEX ────────────────────────────────────────────────────────────
@app.route('/')
def index():
    if not logado(): return redirect('/login')
    conn=sqlite3.connect('banco.db'); cur=conn.cursor()
    cur.execute('SELECT * FROM clientes ORDER BY nome')
    clientes=cur.fetchall()
    alertas={}; hoje=datetime.now().date()
    for c in clientes:
        cid=c[0]; ultima=None
        for tbl in ['metricas_meta','metricas_google','metricas_reels']:
            cur.execute(f'SELECT data FROM {tbl} WHERE cliente_id=? ORDER BY data DESC LIMIT 1',(cid,))
            r=cur.fetchone()
            if r:
                try:
                    d=datetime.strptime(r[0],'%Y-%m-%d').date()
                    if ultima is None or d>ultima: ultima=d
                except Exception: pass
        alertas[cid]=('sem-dados' if ultima is None else ('atrasado' if (hoje-ultima).days>10 else 'ok'))
    conn.close()
    return render_template('index.html', clientes=clientes, alertas=alertas)

@app.route('/excluir-cliente/<int:id>', methods=['POST'])
def excluir_cliente(id):
    if not logado(): return redirect('/login')
    conn=sqlite3.connect('banco.db'); cur=conn.cursor()
    for t in ['metricas_meta','metricas_google','metricas_reels','metas','ganchos','eventos']:
        cur.execute(f'DELETE FROM {t} WHERE cliente_id=?',(id,))
    cur.execute('DELETE FROM clientes WHERE id=?',(id,))
    conn.commit(); conn.close(); return redirect('/')

@app.route('/novo-cliente', methods=['GET', 'POST'])
def novo_cliente():
    if not logado(): return redirect('/login')
    if request.method=='POST':
        conn=sqlite3.connect('banco.db')
        conn.execute('INSERT INTO clientes (nome,segmento,email) VALUES (?,?,?)',
            (request.form['nome'],request.form['segmento'],
             request.form.get('email_cliente','').strip().lower()))
        conn.commit(); conn.close(); return redirect('/')
    return render_template('novo_cliente.html')

@app.route('/cliente/<int:id>')
def cliente(id):
    if not logado(): return redirect('/login')
    conn=sqlite3.connect('banco.db'); cur=conn.cursor()
    cur.execute('SELECT * FROM clientes WHERE id=?',(id,)); cliente=cur.fetchone()
    cur.execute('SELECT * FROM metricas_meta   WHERE cliente_id=? ORDER BY data DESC',(id,)); meta=cur.fetchall()
    cur.execute('SELECT * FROM metricas_google WHERE cliente_id=? ORDER BY data DESC',(id,)); google=cur.fetchall()
    cur.execute('SELECT * FROM metricas_reels  WHERE cliente_id=? ORDER BY data DESC',(id,)); reels=cur.fetchall()
    cur.execute('SELECT * FROM metas WHERE cliente_id=?',(id,)); metas=cur.fetchone()
    conn.close()
    return render_template('cliente.html',cliente=cliente,meta=meta,google=google,reels=reels,metas=metas)

@app.route('/inserir/<int:id>', methods=['GET', 'POST'])
def inserir(id):
    if not logado(): return redirect('/login')
    if request.method=='POST':
        canal=request.form['canal']; data=request.form['data']
        conn=sqlite3.connect('banco.db'); cur=conn.cursor()
        if canal=='meta':
            cur.execute('''INSERT INTO metricas_meta (cliente_id,data,cpm,cpc,ctr,roas,cpa,frequencia,conversoes)
                VALUES (?,?,?,?,?,?,?,?,?)''',
                (id,data,request.form['cpm'],request.form['cpc'],request.form['ctr'],
                 request.form['roas'],request.form['cpa'],request.form['frequencia'],request.form['conversoes']))
        elif canal=='google':
            cur.execute('''INSERT INTO metricas_google (cliente_id,data,impressoes,ctr,cpc,cpa,roas,conversoes,parcela_impressao)
                VALUES (?,?,?,?,?,?,?,?,?)''',
                (id,data,request.form['impressoes'],request.form['ctr'],request.form['cpc'],
                 request.form['cpa'],request.form['roas'],request.form['conversoes'],request.form['parcela_impressao']))
        elif canal=='reels':
            cur.execute('''INSERT INTO metricas_reels (cliente_id,data,nome_video,views,retencao,alcance,curtidas,comentarios,compartilhamentos,salvamentos)
                VALUES (?,?,?,?,?,?,?,?,?,?)''',
                (id,data,request.form['nome_video'],request.form['views'],request.form['retencao'],
                 request.form['alcance'],request.form['curtidas'],request.form['comentarios'],
                 request.form['compartilhamentos'],request.form['salvamentos']))
        conn.commit(); conn.close(); return redirect(f'/cliente/{id}')
    return render_template('inserir.html', id=id)


# ─── REVIEW SEMANAL ───────────────────────────────────────────────────
@app.route('/review/<int:id>')
def review(id):
    if not logado(): return redirect('/login')
    conn=sqlite3.connect('banco.db'); cur=conn.cursor()
    cur.execute('SELECT * FROM clientes WHERE id=?',(id,)); cliente=cur.fetchone()
    cur.execute('''SELECT DISTINCT data FROM (
        SELECT data FROM metricas_meta WHERE cliente_id=?
        UNION SELECT data FROM metricas_google WHERE cliente_id=?
        UNION SELECT data FROM metricas_reels  WHERE cliente_id=?
    ) ORDER BY data DESC''',(id,id,id))
    semanas=[r[0] for r in cur.fetchall()]
    semana_atual=request.args.get('semana',semanas[0] if semanas else None)
    meta_semana=google_semana=meta_ant=google_ant=None; reels_semana=reels_ant=[]
    if semana_atual and semanas:
        idx=semanas.index(semana_atual) if semana_atual in semanas else 0
        sem_ant=semanas[idx+1] if idx+1<len(semanas) else None
        cur.execute('SELECT * FROM metricas_meta   WHERE cliente_id=? AND data=?',(id,semana_atual)); meta_semana=cur.fetchone()
        cur.execute('SELECT * FROM metricas_google WHERE cliente_id=? AND data=?',(id,semana_atual)); google_semana=cur.fetchone()
        cur.execute('SELECT * FROM metricas_reels  WHERE cliente_id=? AND data=?',(id,semana_atual)); reels_semana=cur.fetchall()
        if sem_ant:
            cur.execute('SELECT * FROM metricas_meta   WHERE cliente_id=? AND data=?',(id,sem_ant)); meta_ant=cur.fetchone()
            cur.execute('SELECT * FROM metricas_google WHERE cliente_id=? AND data=?',(id,sem_ant)); google_ant=cur.fetchone()
            cur.execute('SELECT * FROM metricas_reels  WHERE cliente_id=? AND data=?',(id,sem_ant)); reels_ant=cur.fetchall()
    cur.execute('SELECT * FROM metricas_meta   WHERE cliente_id=? ORDER BY data DESC',(id,)); meta=cur.fetchall()
    cur.execute('SELECT * FROM metricas_google WHERE cliente_id=? ORDER BY data DESC',(id,)); google=cur.fetchall()
    cur.execute('SELECT * FROM metricas_reels  WHERE cliente_id=? ORDER BY data DESC',(id,)); reels=cur.fetchall()
    conn.close()
    historico_meta=list(reversed(meta)); historico_google=list(reversed(google)); historico_reels=list(reversed(reels))
    ac=0
    if meta_semana:
        ac+=2 if float(meta_semana[6] or 0)<1.5 else (1 if float(meta_semana[6] or 0)<3 else 0)
        ac+=1 if float(meta_semana[8] or 0)>3.5 else 0
    if google_semana:
        ac+=2 if float(google_semana[7] or 0)<2 else (1 if float(google_semana[7] or 0)<4 else 0)
    if reels_semana:
        ac+=2 if float(reels_semana[0][5] or 0)<25 else (1 if float(reels_semana[0][5] or 0)<40 else 0)
    if not meta_semana and not google_semana and not reels_semana: sc,st='status-neutro','Sem dados'
    elif ac>=3: sc,st='status-critico','Critico'
    elif ac>=1: sc,st='status-atencao','Atencao'
    else: sc,st='status-saudavel','Saudavel'
    dados_ia={}
    if meta_semana:
        dados_ia['meta']={'cpm':meta_semana[3],'cpc':meta_semana[4],'ctr':meta_semana[5],
            'roas':meta_semana[6],'cpa':meta_semana[7],'frequencia':meta_semana[8],'conversoes':meta_semana[9]}
    if google_semana:
        dados_ia['google']={'impressoes':google_semana[3],'ctr':google_semana[4],'cpc':google_semana[5],
            'cpa':google_semana[6],'roas':google_semana[7],'conversoes':google_semana[8],'parcela_impressao':google_semana[9]}
    if reels_semana:
        dados_ia['reels']=[{'nome_video':r[3],'views':r[4],'retencao':r[5],'alcance':r[6],
            'curtidas':r[7],'comentarios':r[8],'compartilhamentos':r[9],'salvamentos':r[10]} for r in reels_semana]
    return render_template('review.html',
        cliente=cliente,semanas=semanas,semana_atual=semana_atual,
        meta_semana=meta_semana,google_semana=google_semana,reels_semana=reels_semana,
        meta_ant=meta_ant,google_ant=google_ant,reels_ant=reels_ant,
        meta=meta,google=google,reels=reels,
        historico_meta=historico_meta,historico_google=historico_google,historico_reels=historico_reels,
        status_classe=sc,status_texto=st,dados_ia=dados_ia)


# ─── RELATORIO BI ─────────────────────────────────────────────────────
@app.route('/relatorio/<int:id>')
def relatorio(id):
    if not logado(): return redirect('/login')
    conn=sqlite3.connect('banco.db'); cur=conn.cursor()
    cur.execute('SELECT * FROM clientes WHERE id=?',(id,)); cliente=cur.fetchone()
    tipo_periodo=request.args.get('tipo','semanal')
    cur.execute('''SELECT DISTINCT data FROM (
        SELECT data FROM metricas_meta WHERE cliente_id=?
        UNION SELECT data FROM metricas_google WHERE cliente_id=?
        UNION SELECT data FROM metricas_reels  WHERE cliente_id=?
    ) ORDER BY data DESC''',(id,id,id))
    semanas=[r[0] for r in cur.fetchall()]
    periodo_atual=request.args.get('periodo',semanas[0] if semanas else None)
    semanas_do_periodo=([s for s in semanas if s.startswith(periodo_atual[:7])]
        if tipo_periodo=='mensal' and periodo_atual else ([periodo_atual] if periodo_atual else []))
    meta_periodo=google_periodo=reels_periodo=[]
    if semanas_do_periodo:
        ph=','.join(['?']*len(semanas_do_periodo))
        cur.execute(f'SELECT * FROM metricas_meta   WHERE cliente_id=? AND data IN ({ph}) ORDER BY data',[id]+semanas_do_periodo); meta_periodo=cur.fetchall()
        cur.execute(f'SELECT * FROM metricas_google WHERE cliente_id=? AND data IN ({ph}) ORDER BY data',[id]+semanas_do_periodo); google_periodo=cur.fetchall()
        cur.execute(f'SELECT * FROM metricas_reels  WHERE cliente_id=? AND data IN ({ph}) ORDER BY data',[id]+semanas_do_periodo); reels_periodo=cur.fetchall()
    cur.execute('SELECT * FROM metricas_meta   WHERE cliente_id=? ORDER BY data',(id,)); historico_meta=cur.fetchall()
    cur.execute('SELECT * FROM metricas_google WHERE cliente_id=? ORDER BY data',(id,)); historico_google=cur.fetchall()
    cur.execute('SELECT * FROM metricas_reels  WHERE cliente_id=? ORDER BY data',(id,)); historico_reels=cur.fetchall()
    conn.close()
    conv_meta=sum(int(m[9] or 0) for m in meta_periodo)
    conv_google=sum(int(g[8] or 0) for g in google_periodo)
    roas_meta=max((float(m[6] or 0) for m in meta_periodo),default=0)
    roas_google=max((float(g[7] or 0) for g in google_periodo),default=0)
    reels_validos=[r for r in reels_periodo if float(r[5] or 0)<=100]
    media_ret=round(sum(float(r[5] or 0) for r in reels_validos)/max(len(reels_validos),1),1) if reels_periodo else 0
    kpis={
        'conversoes_total':conv_meta+conv_google,
        'melhor_roas':round(max(roas_meta,roas_google),2),
        'melhor_roas_canal':'Meta Ads' if roas_meta>=roas_google else 'Google Ads',
        'media_retencao':media_ret,
        'total_reels':len(reels_periodo),
        'canais_ativos':sum([bool(meta_periodo),bool(google_periodo),bool(reels_periodo)]),
    }
    return render_template('relatorio.html',
        cliente=cliente,semanas=semanas,periodo_atual=periodo_atual,tipo_periodo=tipo_periodo,
        meta_periodo=meta_periodo,google_periodo=google_periodo,reels_periodo=reels_periodo,
        historico_meta=historico_meta,historico_google=historico_google,historico_reels=historico_reels,
        kpis=kpis)


# ─── METAS ────────────────────────────────────────────────────────────
@app.route('/metas/<int:id>', methods=['GET', 'POST'])
def metas(id):
    if not logado(): return redirect('/login')
    conn=sqlite3.connect('banco.db'); cur=conn.cursor()
    cur.execute('SELECT * FROM clientes WHERE id=?',(id,)); cliente=cur.fetchone()
    if request.method=='POST':
        cur.execute('''INSERT INTO metas (cliente_id,roas_meta,cpa_meta,ctr_meta,retencao_meta)
            VALUES (?,?,?,?,?) ON CONFLICT(cliente_id) DO UPDATE SET
            roas_meta=excluded.roas_meta,cpa_meta=excluded.cpa_meta,
            ctr_meta=excluded.ctr_meta,retencao_meta=excluded.retencao_meta''',
            (id,request.form.get('roas_meta') or None,request.form.get('cpa_meta') or None,
             request.form.get('ctr_meta') or None,request.form.get('retencao_meta') or None))
        conn.commit(); conn.close(); return redirect(f'/cliente/{id}')
    cur.execute('SELECT * FROM metas WHERE cliente_id=?',(id,)); meta=cur.fetchone(); conn.close()
    return render_template('metas.html',cliente=cliente,meta=meta)


# ─── GANCHOS ──────────────────────────────────────────────────────────
@app.route('/ganchos/<int:id>')
def ganchos(id):
    if not logado(): return redirect('/login')
    conn=sqlite3.connect('banco.db'); cur=conn.cursor()
    cur.execute('SELECT * FROM clientes WHERE id=?',(id,)); cliente=cur.fetchone()
    cur.execute('SELECT * FROM ganchos WHERE cliente_id=? ORDER BY criado_em DESC',(id,)); ganchos_list=cur.fetchall()
    conn.close(); return render_template('ganchos.html',cliente=cliente,ganchos=ganchos_list)

@app.route('/ganchos/<int:id>/novo', methods=['POST'])
def novo_gancho(id):
    if not logado(): return redirect('/login')
    conn=sqlite3.connect('banco.db')
    conn.execute('INSERT INTO ganchos (cliente_id,texto,categoria,retencao,data_uso) VALUES (?,?,?,?,?)',
        (id,request.form['texto'],request.form.get('categoria','Geral'),
         request.form.get('retencao') or None,request.form.get('data_uso') or None))
    conn.commit(); conn.close(); return redirect(f'/ganchos/{id}')

@app.route('/ganchos/excluir/<int:id>', methods=['POST'])
def excluir_gancho(id):
    if not logado(): return redirect('/login')
    conn=sqlite3.connect('banco.db'); cur=conn.cursor()
    cur.execute('SELECT cliente_id FROM ganchos WHERE id=?',(id,)); row=cur.fetchone()
    cur.execute('DELETE FROM ganchos WHERE id=?',(id,))
    conn.commit(); conn.close(); return redirect(f'/ganchos/{row[0]}' if row else '/')


# ─── CALENDARIO ───────────────────────────────────────────────────────
@app.route('/calendario/<int:id>')
def calendario(id):
    if not logado(): return redirect('/login')
    conn=sqlite3.connect('banco.db'); cur=conn.cursor()
    cur.execute('SELECT * FROM clientes WHERE id=?',(id,)); cliente=cur.fetchone()
    cur.execute('SELECT * FROM eventos WHERE cliente_id=? ORDER BY data_evento',(id,)); eventos_list=cur.fetchall()
    cur.execute('SELECT id,nome FROM clientes ORDER BY nome'); todos_clientes=cur.fetchall()
    conn.close()
    return render_template('calendario.html',cliente=cliente,eventos=eventos_list,todos_clientes=todos_clientes)

@app.route('/calendario/<int:id>/novo', methods=['POST'])
def novo_evento(id):
    if not logado(): return redirect('/login')
    conn=sqlite3.connect('banco.db'); cur=conn.cursor()
    titulo=request.form['titulo']; tipo=request.form['tipo']
    data_evento=request.form['data_evento']; hora=request.form.get('hora','')
    descricao=request.form.get('descricao',''); email_conv=request.form.get('email_convite','').strip().lower()
    cur.execute('INSERT INTO eventos (cliente_id,titulo,tipo,data_evento,hora,descricao) VALUES (?,?,?,?,?,?)',
        (id,titulo,tipo,data_evento,hora,descricao))
    conn.commit()
    if email_conv and tipo=='reuniao':
        try: data_fmt=datetime.strptime(data_evento,'%Y-%m-%d').strftime('%d/%m/%Y')
        except Exception: data_fmt=data_evento
        hora_fmt=hora if hora else 'Horario a definir'
        dt=data_evento.replace('-','')
        if hora:
            h_ini=hora.replace(':','')+'00'
            h_end=str(int(hora.split(':')[0])+1).zfill(2)+hora.split(':')[1]+'00'
            gcal_dates=f'{dt}T{h_ini}/{dt}T{h_end}'
        else: gcal_dates=f'{dt}/{dt}'
        gcal_link='https://calendar.google.com/calendar/render?'+urlencode({
            'action':'TEMPLATE','text':titulo,'dates':gcal_dates,
            'details':(descricao or '')+'\n\nAgendado pelo Amigo Gestor'})
        html_email=f'''<div style="font-family:Arial,sans-serif;max-width:520px;margin:auto;
            background:#0f172a;color:#e2e8f0;padding:32px;border-radius:12px;">
          <h2 style="color:#93c5fd;">Convite de Reuniao</h2>
          <div style="background:#0a0f1e;border-radius:10px;padding:20px;margin:20px 0;">
            <p style="font-size:18px;font-weight:700;margin-bottom:12px;">{titulo}</p>
            <p style="color:#94a3b8;margin:6px 0;">Data: <strong style="color:#e2e8f0;">{data_fmt}</strong></p>
            <p style="color:#94a3b8;margin:6px 0;">Horario: <strong style="color:#e2e8f0;">{hora_fmt}</strong></p>
            {'<p style="color:#94a3b8;margin-top:12px;">'+descricao+'</p>' if descricao else ''}
          </div>
          <a href="{gcal_link}" style="display:inline-block;padding:12px 24px;background:#1e3a5f;
            color:#93c5fd;border-radius:8px;text-decoration:none;font-weight:700;">Adicionar ao Google Calendar</a>
        </div>'''
        enviar_email(email_conv,f'Reuniao: {titulo} - {data_fmt}',html_email)
    conn.close(); return redirect(f'/calendario/{id}')

@app.route('/calendario/excluir/<int:id>', methods=['POST'])
def excluir_evento(id):
    if not logado(): return redirect('/login')
    conn=sqlite3.connect('banco.db'); cur=conn.cursor()
    cur.execute('SELECT cliente_id FROM eventos WHERE id=?',(id,)); row=cur.fetchone()
    cur.execute('DELETE FROM eventos WHERE id=?',(id,))
    conn.commit(); conn.close(); return redirect(f'/calendario/{row[0]}' if row else '/')

@app.route('/api/eventos/<int:cliente_id>')
def api_eventos(cliente_id):
    if not logado(): return jsonify([])
    conn=sqlite3.connect('banco.db'); cur=conn.cursor()
    cur.execute('SELECT * FROM eventos WHERE cliente_id=? ORDER BY data_evento',(cliente_id,))
    rows=cur.fetchall(); conn.close()
    CORES={'postagem':'#ec4899','review':'#3b82f6','metricas':'#f59e0b','campanha':'#22c55e','reuniao':'#a78bfa','outro':'#64748b'}
    return jsonify([{'id':r[0],'title':r[2],'start':r[4]+('T'+r[5] if r[5] else ''),
        'backgroundColor':CORES.get(r[3],'#64748b'),'borderColor':CORES.get(r[3],'#64748b'),
        'extendedProps':{'tipo':r[3],'descricao':r[6] or ''}} for r in rows])


# ─── EDITAR / EXCLUIR METRICAS ────────────────────────────────────────
@app.route('/excluir/meta/<int:id>', methods=['POST'])
def excluir_meta(id):
    if not logado(): return redirect('/login')
    conn=sqlite3.connect('banco.db'); cur=conn.cursor()
    cur.execute('SELECT cliente_id FROM metricas_meta WHERE id=?',(id,)); row=cur.fetchone()
    cur.execute('DELETE FROM metricas_meta WHERE id=?',(id,))
    conn.commit(); conn.close(); return redirect(f'/cliente/{row[0]}' if row else '/')

@app.route('/excluir/google/<int:id>', methods=['POST'])
def excluir_google(id):
    if not logado(): return redirect('/login')
    conn=sqlite3.connect('banco.db'); cur=conn.cursor()
    cur.execute('SELECT cliente_id FROM metricas_google WHERE id=?',(id,)); row=cur.fetchone()
    cur.execute('DELETE FROM metricas_google WHERE id=?',(id,))
    conn.commit(); conn.close(); return redirect(f'/cliente/{row[0]}' if row else '/')

@app.route('/excluir/reels/<int:id>', methods=['POST'])
def excluir_reels(id):
    if not logado(): return redirect('/login')
    conn=sqlite3.connect('banco.db'); cur=conn.cursor()
    cur.execute('SELECT cliente_id FROM metricas_reels WHERE id=?',(id,)); row=cur.fetchone()
    cur.execute('DELETE FROM metricas_reels WHERE id=?',(id,))
    conn.commit(); conn.close(); return redirect(f'/cliente/{row[0]}' if row else '/')

@app.route('/editar/meta/<int:id>', methods=['GET','POST'])
def editar_meta(id):
    if not logado(): return redirect('/login')
    conn=sqlite3.connect('banco.db'); cur=conn.cursor()
    if request.method=='POST':
        cur.execute('''UPDATE metricas_meta SET data=?,cpm=?,cpc=?,ctr=?,roas=?,cpa=?,frequencia=?,conversoes=? WHERE id=?''',
            (request.form['data'],request.form['cpm'],request.form['cpc'],request.form['ctr'],
             request.form['roas'],request.form['cpa'],request.form['frequencia'],request.form['conversoes'],id))
        conn.commit(); row=cur.execute('SELECT cliente_id FROM metricas_meta WHERE id=?',(id,)).fetchone()
        conn.close(); return redirect(f'/cliente/{row[0]}')
    cur.execute('SELECT * FROM metricas_meta WHERE id=?',(id,)); m=cur.fetchone(); conn.close()
    return render_template('editar_meta.html',m=m)

@app.route('/editar/google/<int:id>', methods=['GET','POST'])
def editar_google(id):
    if not logado(): return redirect('/login')
    conn=sqlite3.connect('banco.db'); cur=conn.cursor()
    if request.method=='POST':
        cur.execute('''UPDATE metricas_google SET data=?,impressoes=?,ctr=?,cpc=?,cpa=?,roas=?,conversoes=?,parcela_impressao=? WHERE id=?''',
            (request.form['data'],request.form['impressoes'],request.form['ctr'],request.form['cpc'],
             request.form['cpa'],request.form['roas'],request.form['conversoes'],request.form['parcela_impressao'],id))
        conn.commit(); row=cur.execute('SELECT cliente_id FROM metricas_google WHERE id=?',(id,)).fetchone()
        conn.close(); return redirect(f'/cliente/{row[0]}')
    cur.execute('SELECT * FROM metricas_google WHERE id=?',(id,)); m=cur.fetchone(); conn.close()
    return render_template('editar_google.html',m=m)

@app.route('/editar/reels/<int:id>', methods=['GET','POST'])
def editar_reels(id):
    if not logado(): return redirect('/login')
    conn=sqlite3.connect('banco.db'); cur=conn.cursor()
    if request.method=='POST':
        cur.execute('''UPDATE metricas_reels SET data=?,nome_video=?,views=?,retencao=?,alcance=?,curtidas=?,comentarios=?,compartilhamentos=?,salvamentos=? WHERE id=?''',
            (request.form['data'],request.form['nome_video'],request.form['views'],request.form['retencao'],
             request.form['alcance'],request.form['curtidas'],request.form['comentarios'],
             request.form['compartilhamentos'],request.form['salvamentos'],id))
        conn.commit(); row=cur.execute('SELECT cliente_id FROM metricas_reels WHERE id=?',(id,)).fetchone()
        conn.close(); return redirect(f'/cliente/{row[0]}')
    cur.execute('SELECT * FROM metricas_reels WHERE id=?',(id,)); m=cur.fetchone(); conn.close()
    return render_template('editar_reels.html',m=m)


if __name__ == '__main__':
    app.run(debug=True)