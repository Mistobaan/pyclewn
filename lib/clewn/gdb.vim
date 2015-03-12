" vi:set ts=8 sts=4 sw=4 et tw=80:
" Pyclewn gdb commands and completion.

function! <SID>goto_breakpoint()
    let l:line = getline(".")
    let l:regexp = '^\(.*\) at \(.\+\):\(\d\+\) <\(.\+\)>$'
    let l:lnum = substitute(l:line, l:regexp , '\3', "")
    if l:line != l:lnum
        let l:fname = substitute(l:line, l:regexp , '\4', "")
        if filereadable(l:fname)
            call pyclewn#buffers#GotoBreakpoint(l:fname, l:lnum)
        endif
    endif
endfunction

function! <SID>goto_frame()
    let l:line = getline(".")
    let l:regexp = '^\([ *] \)#\(\d\+\).*$'
    let l:id = substitute(l:line, l:regexp , '\2', "")
    if l:line != l:id
        let l:regexp = '^\([ *] \)#\(\d\+\).* at \(.\+\) <\(.\+\)>$'
        let l:fname = substitute(l:line, l:regexp , '\4', "")
        if l:line != l:fname && filereadable(l:fname)
            call pyclewn#buffers#GotoFrame(l:fname)
        endif
        exe "Cframe " . l:id
    endif
endfunction

function! <SID>goto_thread()
    let l:line = getline(".")
    let l:regexp = '^\([ *] \)\(\d\+\).*$'
    let l:thread = substitute(l:line, l:regexp , '\2', "")
    if l:line != l:thread
        " Search for a source code window.
        let l:count = winnr("$")
        let l:nr = 1
        while l:nr <= l:count
            if bufname(winbufnr(l:nr)) !~# "^(clewn)_"
                exe l:nr . "wincmd w"
                break
            endif
            let l:nr = l:nr + 1
        endwhile

        exe "Cthread " . l:thread
    endif
endfunction

" Implement the 'define', 'commands' and 'document' gdb commands.
function! s:error(msg)
    echohl ErrorMsg
    echo a:msg
    call inputsave()
    call input("Press the <Enter> key to continue.")
    call inputrestore()
    echohl None
endfunction

function! s:source_commands(gdb_cmd, prompt)
    " input user commands
    let l:prompt = a:prompt . ", one per line.\n"
    let l:prompt .= "End with a line saying just 'end'.\n"
    let l:prompt .= "These commands are then sourced by the"
    \               . " 'Csource' gdb command.\n"
    let l:prompt .= ">"

    let l:commands = [a:gdb_cmd]
    call inputsave()
    while 1
        let l:cmd = input(l:prompt)
        let l:commands += [l:cmd]
        echo "\n"
        let l:prompt = ">"
        if substitute(l:cmd, " ", "", "g") == "end"
            break
        endif
    endwhile
    call inputrestore()

    " store them in a file and source the file
    let l:tmpfile = tempname()
    call writefile(commands, l:tmpfile)
    exe "%(pre)ssource " . l:tmpfile
endfunction

function! s:define(...)
    if a:0 != 1
        call s:error("One argument required (name of command to define).")
        return
    endif
    call s:source_commands("define " . a:1,
    \       "Type commands for definition of '" . a:1 . "'")
endfunction

function! s:document(...)
    if a:0 != 1
        call s:error("One argument required (name of command to document).")
        return
    endif
    call s:source_commands("document " . a:1,
    \       "Type documentation for '" . a:1 . "'")
endfunction

function! s:commands(...)
    if a:0 == 0
        call s:error("Argument required (one or more breakpoint numbers).")
        return
    endif
    for bp in a:000
        let l:x = "" + bp
        if l:x == 0
            call s:error("Not a breakpoint number: '" . bp . "'")
            return
        endif
    endfor
    let l:bplist = join(a:000)
    call s:source_commands("command " . l:bplist,
    \       "Type commands for breakpoint(s) " . l:bplist . "")
endfunction

command! -bar -nargs=* %(pre)sdefine call s:define(<f-args>)
command! -bar -nargs=* %(pre)sdocument call s:document(<f-args>)
command! -bar -nargs=* %(pre)scommands call s:commands(<f-args>)

function! s:GdbComplete(arglead, cmdline, curpos)
    call writefile([], %(ack_tmpfile)s)
    let l:start = localtime()
    if stridx(a:cmdline, "%(pre)s") == 0
        let l:cmdline = a:cmdline[1:]
    else
        let l:cmdline = a:cmdline
    endif
    exe "nbkey complete " . l:cmdline

    while 1
        " Pyclewn signals that complete_tmpfile is ready for reading.
        if getfsize(%(ack_tmpfile)s) > 0
            if join(readfile(%(ack_tmpfile)s), "") != "Ok"
                return []
            endif
            return readfile(%(complete_tmpfile)s)
        endif

        " The time out has expired.
        if localtime() - l:start > %(completion_timeout)s
            return []
        endif
        sleep 100m
    endwhile
endfunction

autocmd clewn BufAdd (clewn)_* call s:init_gdb_completion()

" Initialize full gdb completion only once, after the first debugging session
" has been started.
let s:gdb_completion_done = 0
function s:init_gdb_completion()
    if s:gdb_completion_done
        return
    endif
    let s:gdb_completion_done = 1

    %(commands)s
endfunction

