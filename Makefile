build:
	docker build -t form2yaml .

up:
	mkdir -p templates snapshots
	docker rm -f form2yaml 2>/dev/null || true
	docker run -d \
		--name form2yaml \
		-p 8000:8000 \
		-v "$(PWD)/templates:/app/templates" \
		-v "$(PWD)/snapshots:/app/snapshots" \
		form2yaml

logs:
	docker logs -f form2yaml

status:
	docker ps | grep form2yaml || true

restart: down up

down:
	docker rm -f form2yaml