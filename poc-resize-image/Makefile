
build:
	@docker build -t poc-resize-image .

run:
	@docker run --rm -p 8081:80 poc-resize-image

create-repo-artifacts:
	gcloud artifacts repositories create poc --repository-format=docker \
	--location=us-central1 --description="Repository for poc"

configure-repo-artifacts:
	gcloud auth configure-docker us-central1-docker.pkg.dev

add-image-artifacts:
	@docker tag poc-resize-image:latest us-central1-docker.pkg.dev/plated-cabinet-356100/poc/poc-resize-image:latest
	@docker push us-central1-docker.pkg.dev/plated-cabinet-356100/poc/poc-resize-image:latest