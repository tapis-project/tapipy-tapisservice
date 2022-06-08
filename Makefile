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
	rm -rf dist
	docker build -t tapis/flaskbase -f Dockerfile-flask .

build-test:
	rm -rf dist
	docker build -t tapis/tapisservice-tests -f Dockerfile-tests .

run-tests:
	docker run $$interactive --rm  tapis/tapisservice-tests

test: build-flask build-test run-tests

docker-only: build-flask test-only
