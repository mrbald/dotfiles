#!/bin/bash

# store the encrypted password in the text file ~/git_password.txt using the below cmdline (add an extra space in front of the command, so it bypasses the Bash history file):
# $  openssl rsautl -encrypt -pubin -inkey <(ssh-keygen -f ~/.ssh/id_rsa.pub -e -m PKCS8) -ssl -in <(echo '$$$YourPassword$$$') -out >(base64 > ~/git_password.txt)
# point git to this file with:
# $ git config --global --add core.askPass ~/git_password.sh
if [[ $1 =~ github.com ]]; then
    openssl rsautl -decrypt -inkey ~/.ssh/id_rsa -in <(base64 -d < ~/git_password.txt) -out >(cat)
else
    exit 1
fi
