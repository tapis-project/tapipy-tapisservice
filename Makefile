# Makefile for local development

ifdef in_jenkins
unexport interactive
else
export interactive := -it
endif


build:	
	rm -rf dist
	poetry build
	
install: build
	pip3 uninstall tapisservice -y
	pip3 install dist/*.whl

build-flask: 
	docker build -t tapis/flaskbase -f Dockerfile-flask .

build-test:
	docker build -t tapis/tapisservice-tests -f Dockerfile-tests .

test: build-flask build-test
	docker run $$interactive --rm  tapis/tapisservice-tests

docker-only: build-flask test-only
