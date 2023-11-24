# PoC para upload de diretórios

# Dependencias
- python
- docker
- apache2  ou httpd


## Referências
[Instalando e configurando apache2](https://www.digitalocean.com/community/tutorials/how-to-install-the-apache-web-server-on-ubuntu-20-04-pt)

[SSE push notifications](https://python.plainenglish.io/server-sent-events-for-push-notifications-on-fastapi-73e7ac4a2c2e)


## Como executar?

Executando backend:
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cd upload-fastapi
make run
```

Abra no navegador o arquivo index.html