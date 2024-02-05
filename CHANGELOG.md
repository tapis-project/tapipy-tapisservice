# Change Log
All notable changes to this project will be documented in this file.

## 1.6.0 - 2024-02-05
Tapipy is now using `tapipy==1.6.0`

## 1.5.0 - 2023-12-05
Fixed `ERROR: request_thread_local missing token_claims! attrs: ['__class__', .....]` logs. Was not an error.
Pruned some logs.

## 1.4.1 - 2023-10-04
Updating tapipy to 1.4.1 from 1.4.0

## 1.4.0 - 2023-06-12
TapisService now using `tapipy==1.4.0`. This version overhauls the spec backend previously used for quick imports.
Spec is now read as a dictionary so small changes were implemented to change from attr notation to dict notation.
Newest openapi-spec library enforces validated object output as frozen, we override that in `utils.py` to keep
service code working as is.
We pin `sqlalchemy==1.4.48` as otherwise sqlalchemy attempts to download to 2+ which breaks tapisflask.

## 1.3.0 - 2023-03-01
`request_thread_local.request_username` is now set. Previously, `request_thread_local.username` was set equal to the token
claims `username` field, and `request_thread_local.x_tapis_user` was set equal to the `_x_tapis_user` incoming headers
that service accounts are allowed to set in order to run as other users. This meant that it was up to the services to
negotiate which username variable to use. `x_tapis_user` in that case gets ignored as only service accounts use it. From
now on services should make use of `request_username` to get either the regular token username, or if provided, the
username a service account is making a request on behalf of.
To note, this is secure. The possible issue would be if we had primary site, A, and associate site, B. There could be a
scenario where a service from B could try and run as another user on A. This behaviour is forbidden by 
`tapisservice.auth.service_token_checks()`. This restricts associate sites from cross site service requests. Only the
primary site is allowed that permission.

## 1.2.6 - 2022-10-28
Fix, one tenants section was attempting to call Tapis with resource_set=local.
Adding dev_request_url conf to divert request with said url to dev tenant.

## 1.2.5 - 2022-06-08
Fix, had lost decode algorithms code and FastAPI g initialization in init.

## 1.2.4 - 2022-06-08
tapisservice now sets tenants as a dictionary of tenant_id: tenant_obj key-pairs to match Tapipy's implementation.

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