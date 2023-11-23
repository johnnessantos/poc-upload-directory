run:
	@uvicorn upload_file:app --host=0.0.0.0 --port=8080 --proxy-headers


ws-run:
	@uvicorn ws:app --reload


deploy-frontend:
	@sudo cp index.html /var/www/html/index.html
	@sudo systemctl restart apache2
