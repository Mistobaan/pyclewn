" vi:set ts=8 sts=4 sw=4 et tw=80:
" Pyclewn gdb commands and completion.

augroup clewn
    autocmd BufWinEnter (clewn)_variables silent! setlocal syntax=clewn_variables
    autocmd BufEnter (clewn)_variables nnoremap <buffer> <silent> <CR> :exe "%(pre)sfoldvar " . line(".")<CR>
    autocmd BufEnter (clewn)_variables nnoremap <buffer> <silent> <2-Leftmouse> :exe "%(pre)sfoldvar " . line(".")<CR>

    autocmd BufEnter (clewn)_breakpoints nnoremap <buffer> <silent> <CR> :call <SID>goto_breakpoint()<CR>
    autocmd BufEnter (clewn)_breakpoints nnoremap <buffer> <silent> <2-Leftmouse> :call <SID>goto_breakpoint()<CR>
    autocmd BufEnter (clewn)_breakpoints nnoremap <buffer> <silent> + :call <SID>toggle_breakpoint()<CR>
    autocmd BufEnter (clewn)_breakpoints nnoremap <buffer> <silent> <C-K> :call <SID>delete_breakpoint()<CR>

    autocmd BufEnter (clewn)_backtrace nnoremap <buffer> <silent> <CR> :call <SID>goto_frame()<CR>
    autocmd BufEnter (clewn)_backtrace nnoremap <buffer> <silent> <2-Leftmouse> :call <SID>goto_frame()<CR>

    autocmd BufEnter (clewn)_threads nnoremap <buffer> <silent> <CR> :call <SID>goto_thread()<CR>
    autocmd BufEnter (clewn)_threads nnoremap <buffer> <silent> <2-Leftmouse> :call <SID>goto_thread()<CR>
augroup END

function! s:parse_breakpoint_curline()
    let l:rv = []
    let l:line = getline(".")
    let l:regexp = '^\(\d\+\)\s\+\S\+\s\+\([yn]\).* at .\+:\(\d\+\) <\(.\+\)>$'
    let l:lnum = substitute(l:line, l:regexp , '\3', "")
    if l:line != l:lnum
        call add(l:rv, substitute(l:line, l:regexp , '\1', ""))
        call add(l:rv, substitute(l:line, l:regexp , '\2', ""))
        call add(l:rv, l:lnum)
        call add(l:rv, substitute(l:line, l:regexp , '\4', ""))
    endif
    return l:rv
endfunction

function! <SID>goto_breakpoint()
    let l:bp = s:parse_breakpoint_curline()
    if len(l:bp)
        let l:fname = l:bp[3]
        if filereadable(l:fname)
            call pyclewn#buffers#GotoBreakpoint(l:fname, l:bp[2])
        endif
    endif
endfunction

function! <SID>toggle_breakpoint()
    let l:bp = s:parse_breakpoint_curline()
    if len(l:bp)
        if l:bp[1] == "y"
            exe "%(pre)sdisable " . l:bp[0]
        else
            exe "%(pre)senable " . l:bp[0]
        endif
    endif
endfunction

function! <SID>delete_breakpoint()
    let l:bp = s:parse_breakpoint_curline()
    if len(l:bp)
        exe "%(pre)sdelete " . l:bp[0]
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
        exe "%(pre)sframe " . l:id
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

        exe "%(pre)sthread " . l:thread
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

function! s:source_commands(gdb_cmd, prompt, extension)
    " input user commands
    let l:prompt = ""
    if a:prompt != ""
        let l:prompt .= a:prompt . ", one per line.\n"
    endif
    let l:prompt .= "End with a line saying just 'end'.\n"
    let l:prompt .= "These commands are then sourced by the"
    \               . " 'source' gdb command.\n"
    let l:prompt .= ">"

    let l:lines = %(source_lines)s
    let l:commands = []
    call inputsave()
    while 1
        let l:cmd = %(input_source)s
        if substitute(l:cmd, " ", "", "g") == "end"
            if a:extension != ".py" && len(l:commands)
                let l:commands += [l:cmd]
            endif
            break
        endif
        let l:commands += [l:cmd]
        echo "\n"
        let l:prompt = ">"
    endwhile
    call inputrestore()

    " store them in a file and source the file
    if len(l:commands)
        if a:gdb_cmd != ""
            call insert(l:commands, a:gdb_cmd)
        endif
        let l:tmpfile = tempname()
        if a:extension != ""
            let l:tmpfile .= a:extension
        endif
        call writefile(l:commands, l:tmpfile)
        exe "%(pre)ssource " . l:tmpfile
    endif
endfunction

function! s:define(...)
    if a:0 != 1
        call s:error("One argument required (name of command to define).")
        return
    endif
    call s:source_commands("define " . a:1,
    \       "Type commands for definition of '" . a:1 . "'", "")
endfunction

function! s:document(...)
    if a:0 != 1
        call s:error("One argument required (name of command to document).")
        return
    endif
    call s:source_commands("document " . a:1,
    \       "Type documentation for '" . a:1 . "'", "")
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
    \       "Type commands for breakpoint(s) " . l:bplist . "", "")
endfunction

function! s:python(...)
    if a:0 != 0
        exe "%(pre)s python ". join(a:000)
        return
    endif
    call s:source_commands("", "", ".py")
endfunction

command! -bar -nargs=* %(pre)sdefine call s:define(<f-args>)
command! -bar -nargs=* %(pre)sdocument call s:document(<f-args>)
command! -bar -nargs=* %(pre)scommands call s:commands(<f-args>)
command! -bar -nargs=* %(pre)spython call s:python(<f-args>)

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

" Setup full gdb completion.
function! s:runonce_dict.init_gdb_completion() dict
    %(commands)s
endfunction

