#!/bin/bash

# echo "args: $1" >&2
if [[ $1 =~ github.com ]]; then
    openssl rsautl -decrypt -inkey ~/.ssh/id_rsa -in <(base64 -d < ~/git_password.txt) -out >(cat)
else
    exit 1
fi
