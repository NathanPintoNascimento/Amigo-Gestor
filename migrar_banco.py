"""
Execute UMA VEZ para atualizar o banco existente:
    python migrar_banco.py
"""
import sqlite3, hashlib, secrets, getpass, sys

conn = sqlite3.connect('banco.db')
c = conn.cursor()

print("🔄 Migrando banco de dados...")

# 1. Tabela usuarios
c.execute('''CREATE TABLE IF NOT EXISTS usuarios (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    nome         VARCHAR(100),
    email        VARCHAR(150) UNIQUE,
    senha_hash   VARCHAR(64),
    verificado   INTEGER DEFAULT 0,
    token_verif  VARCHAR(64),
    criado_em    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)''')
print("  ✓ tabela usuarios")

# 2. Coluna email em clientes (se não existir)
try:
    c.execute('ALTER TABLE clientes ADD COLUMN email VARCHAR(150)')
    print("  ✓ coluna email em clientes")
except Exception:
    print("  · coluna email já existe")

# 3. Tabelas novas (metas, ganchos, eventos) se não existirem
for sql, nome in [
    ('''CREATE TABLE IF NOT EXISTS metas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER UNIQUE,
        roas_meta DECIMAL(5,2), cpa_meta DECIMAL(10,2),
        ctr_meta DECIMAL(5,2), retencao_meta DECIMAL(5,2))''', 'metas'),
    ('''CREATE TABLE IF NOT EXISTS ganchos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER,
        texto TEXT, categoria VARCHAR(50), retencao DECIMAL(5,2),
        data_uso DATE, criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''', 'ganchos'),
    ('''CREATE TABLE IF NOT EXISTS eventos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER,
        titulo VARCHAR(200), tipo VARCHAR(50), data_evento DATE,
        hora VARCHAR(10), descricao TEXT, google_event_id VARCHAR(200),
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''', 'eventos'),
]:
    c.execute(sql)
    print(f"  ✓ tabela {nome}")

conn.commit()

# 4. Criar primeiro usuário admin
print("\n👤 Criar usuário admin")
nome  = input("   Seu nome: ").strip()
email = input("   Seu email: ").strip().lower()
senha = getpass.getpass("   Senha (min 6 chars): ")

if len(senha) < 6:
    print("❌ Senha muito curta. Rode novamente.")
    conn.close(); sys.exit(1)

h = hashlib.sha256(senha.encode()).hexdigest()
try:
    c.execute('INSERT INTO usuarios (nome, email, senha_hash, verificado) VALUES (?,?,?,1)',
              (nome, email, h))
    conn.commit()
    print(f"\n✅ Usuário '{nome}' criado e verificado!")
    print(f"   Email: {email}")
    print(f"\n▶  Agora rode:  python app.py")
    print(f"   E acesse:    http://localhost:5000/login")
except sqlite3.IntegrityError:
    print(f"⚠️  Email já cadastrado. Login com {email} deve funcionar.")
    conn.commit()

conn.close()