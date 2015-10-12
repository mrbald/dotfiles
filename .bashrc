[[ "$-" != *i* ]] && return

[[ ${SSH_CLIENT:-unset} != 'unset' ]] && export DISPLAY=${SSH_CLIENT%% *}:0.0

export PS1='\u@\h> '

alias rm='rm -i'
alias cp='cp -i'
alias mv='mv -i'

alias df='df -h'
alias du='du -h'

alias ll='ls -l'
alias la='ls -A'

alias h='history 100'

export HISTCONTROL=$HISTCONTROL${HISTCONTROL+,}ignoreboth,erasedups
export HISTIGNORE=$'[ \t]*:&:[fb]g:exit:ls'
export PROMPT_COMMAND="history -a"
export HISTSIZE=10000 
shopt -s histappend

set -o ignoreeof 

alias astyle=$(type -P astyle)' --style=allman --indent=spaces=4 --indent-switches --break-blocks --pad-oper --keep-one-line-blocks --keep-one-line-statements --align-pointer=type --align-reference=type --convert-tabs'

# strace with longer strings
alias strace='/usr/bin/strace -v -s 256'

# make with machine load aware number of parallel jobs
alias makeit='/usr/bin/make -l$(nproc) -j$(nproc)'

# shortcut for nedit client; sorry, netcat
alias nc='nedit-client'

# screen with forced detach of others, reconnect to existing; expects name as a param
alias screen='screen -DRS'

# correct time (not a built-in) with correct flags
alias timeit='/usr/bin/time -v -p --'

# creates background ssh session reusable by others (needs specific .ssh/config) 
alias ssh-bg='ssh -Nf'

# ssh with motd suppression
alias ssh-q='ssh -q'

# ssh with security disabled
alias ssh-cowboy='ssh -q -oUserKnownHostsFile=/dev/null -oCheckHostIP=no -oStrictHostKeyChecking=no'

# threads of the pid, usage: ps-threads-list <pid>
alias ps-threads-list='ps --no-headers -ww -L -olwp'

# threads of the pid, usage: ps-threads-tree <pid>
alias ps-threads-tree='pidstat -tw -p'

# watch threads of the process with CPU IDs and CPU %s, sorted by CPU %, usage: ps-threads-watch <pid>
alias ps-threads-watch='watch -n.2 ps -o tid,psr,pcpu,comm --sort=-pcpu -L -p'

# top the threads of a process, usage: top-threads <pid>
alias top-threads='top -Hp'

# process cpu affinity mask, usage: cpu-affinity <pid>
alias cpu-affinity='taskset -p'

# starts a simple server in PWD, accepts optional argument - port
alias httpit='python -m SimpleHTTPServer'

# bash with clean environment
alias bash-sterile='/bin/env -i /bin/bash --noprofile --norc'

# export TMPDIR=/dev/shm/$USER/tmp
# [[ -d $TMPDIR ]] || /bin/mkdir -p $TMPDIR

export PATH=.:${HOME}/bin:${PATH}

function shell-title {
    echo -ne "\033]2;"$@"\007"
}

function screen-title {
    local NEW_TITLE="\033]0;$@\007"
    echo -ne "\033P${NEW_TITLE}\033\\"
}

function screen-name {
    echo -ne '\033k'$@'\033\\'
}

# http://stackoverflow.com/questions/13890789/convert-dmesg-timestamp-to-custom-date-format
function dmesg-for-humans {
    $(type -P dmesg) "$@" | perl -w -e 'use strict;
        my ($uptime) = do { local @ARGV="/proc/uptime";<>}; ($uptime) = ($uptime =~ /^(\d+)\./);
        foreach my $line (<>) {
            printf( ($line=~/^\[\s*(\d+)\.\d+\](.+)/) ? ( "[%s]%s\n", scalar localtime(time - $uptime + $1), $2 ) : $line )
        }'
}

