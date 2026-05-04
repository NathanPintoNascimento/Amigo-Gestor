# Amigo Gestor

Plataforma web para gestores de tráfego acompanharem métricas de clientes em Meta Ads, Google Ads e Reels — tudo em um só lugar.

---

##  Funcionalidades

- **Cadastro e gerenciamento de clientes** com segmento e e-mail
- **Lançamento de métricas** de Meta Ads, Google Ads e Reels por semana
- **Review semanal** com comparativo entre períodos e score de saúde da conta (Saudável / Atenção / Crítico)
- **Relatório BI** com KPIs consolidados por semana ou por mês
- **Metas por cliente** — ROAS, CPA, CTR e retenção de Reels
- **Banco de ganchos** — textos criativos com taxa de retenção por categoria
- **Calendário de eventos** (postagens, reviews, reuniões) com envio de convite por e-mail e link para o Google Calendar
- **Sistema de usuários** com cadastro, login, recuperação de senha e setup inicial
- **Alertas de dados atrasados** no dashboard (sem dados / atrasado / ok)

---

##  Estrutura do Projeto

```
amigo-gestor/
├── app.py                  # Ponto de entrada e todas as rotas
├── requirements.txt        # Dependências Python
└── templates/
    ├── index.html
    ├── login.html
    ├── cadastro.html
    ├── setup.html
    ├── esqueci_senha.html
    ├── redefinir_senha.html
    ├── ajuda.html
    ├── novo_cliente.html
    ├── cliente.html
    ├── inserir.html
    ├── editar_meta.html
    ├── editar_google.html
    ├── editar_reels.html
    ├── review.html
    ├── relatorio.html
    ├── metas.html
    ├── ganchos.html
    └── calendario.html
```

---

##  Como Rodar Localmente

### 1. Clone e configure o ambiente

```bash
git clone https://github.com/seu-usuario/amigo-gestor.git
cd amigo-gestor

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure as variáveis de ambiente

```bash
cp .env.example .env
# Edite o .env com seus valores
```

### 3. Inicie a aplicação

```bash
flask run
# ou, para produção:
gunicorn app:app
```

Acesse [http://localhost:5000](http://localhost:5000). Na primeira abertura você será redirecionado para `/setup` para criar o usuário administrador.

---

##  Variáveis de Ambiente

| Variável        | Descrição                                              |
|-----------------|--------------------------------------------------------|
| `SECRET_KEY`    | Chave secreta para as sessões do Flask                 |
| `DATABASE_PATH` | Caminho do arquivo SQLite (padrão: `banco.db`)         |
| `BASE_URL`      | URL base da aplicação (usada nos links de e-mail)      |
| `EMAIL_USER`    | Endereço Gmail para envio de notificações              |
| `EMAIL_PASS`    | Senha de App do Gmail (não a senha da conta)           |
| `FLASK_DEBUG`   | Use `true` apenas em desenvolvimento                   |



---

##  Schema do Banco de Dados

O banco SQLite é criado automaticamente na primeira execução. As tabelas são:

| Tabela              | Descrição                                      |
|---------------------|------------------------------------------------|
| `usuarios`          | Usuários da plataforma com autenticação        |
| `clientes`          | Clientes gerenciados                           |
| `metricas_meta`     | Métricas semanais do Meta Ads                  |
| `metricas_google`   | Métricas semanais do Google Ads                |
| `metricas_reels`    | Dados de Reels por vídeo                       |
| `metas`             | Metas de ROAS, CPA, CTR e retenção por cliente |
| `ganchos`           | Banco de textos criativos com retenção         |
| `eventos`           | Calendário de eventos por cliente              |

---

##  Segurança

- Senhas armazenadas com hash SHA-256.
- Todas as rotas protegidas verificam a sessão no servidor.
- Credenciais carregadas exclusivamente via variáveis de ambiente.
- Recuperação de senha via token de uso único (`secrets.token_urlsafe`).

---

##  Tecnologias Utilizadas

| Camada        | Tecnologia                          |
|---------------|-------------------------------------|
| Backend       | Python 3 · Flask                    |
| Banco de dados| SQLite · sqlite3                    |
| E-mail        | smtplib · Gmail SMTP SSL            |
| Frontend      | Jinja2 · HTML/CSS                   |
| Deploy        | Gunicorn · Render / Railway / Heroku|

---

##  Licença

Projeto de uso privado. Todos os direitos reservados.
