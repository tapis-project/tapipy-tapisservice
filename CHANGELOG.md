# Change Log
All notable changes to this project will be documented in this file.

## 1.2.3 - 2022-06-07
Tests now rely on a seperate requirements file instead of using fastapi's.
Flask and Fastapi now rely on PyPi version of tapisservice.
Tests rely on local tapisservice.

## 1.2.2 - 2022-05-31
Fixed issue with core_validate_request_token() that was preventing validate_request_token from working for flask services.

## 1.2.1 - 2022-05-20
Simplified dependencies, now works with Python 3.10.
Simplified Dockerfile-tests.

## 1.2.0 - 2022-05-19
Added fastapi functionality.
Added templates for fastapi base image.
Added testing from tapipy repo.
Added testing Dockerfile.

## 1.1.3 - 2022-05-19
Packaged tapisservice and released on PyPi.

## 1.1.0 - 2022-03-01
This is the initial release of the tapisservice python plugin package for the `tapisservice` library. 