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

test: build
	docker build -t tapis/tapisservice-tests -f Dockerfile-tests .
	docker run $$interactive --rm  tapis/tapisservice-tests