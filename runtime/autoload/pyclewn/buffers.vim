" vi:set ts=8 sts=4 sw=4 et tw=80:
" Pyclewn run time file.
" Maintainer:   <xdegaye at users dot sourceforge dot net>
"
" Handle pyclewn buffers.
"
if exists("s:did_buffers")
    finish
endif
let s:did_buffers = 1

"---------------------   AUTOLOAD FUNCTIONS   ---------------------

" Display the console in a window, split if needed. The function is called
" before a 'C' command is executed.
"   'location': the value of the '--window' option, i.e. "top", "bottom",
"               "left", "right" or "none".
function pyclewn#buffers#DisplayConsole(location)
    if exists("*Pyclewn_DisplayConsole")
        call Pyclewn_DisplayConsole(a:location)
        return
    endif
    call s:split_console("(clewn)_console", a:location)
endfunction

" Display the '(clewn)_variables' buffer in a window, split if needed. The
" function is called before the 'Cdbgvar' command is executed and after
" 'Pyclewn_DisplayConsole'.
function pyclewn#buffers#DbgvarSplit()
    if exists("*Pyclewn_DbgvarSplit")
        call Pyclewn_DbgvarSplit()
        return
    endif
    call s:split_console("(clewn)_variables", "")
endfunction

" Display the frame source code in a window. The function is called after the
" <CR> key or the mouse is used in a '(clewn)_backtrace' window. The line number
" is not available (to avoid screen blinks) in this window, but the ensuing
" 'Cframe' command will automatically move the cursor to the right place.
"   'fname': the source code full path name.
function pyclewn#buffers#GotoFrame(fname)
    if exists("*Pyclewn_GotoFrame")
        call Pyclewn_GotoFrame(a:fname)
        return
    endif
    call s:split_source(a:fname, "")
endfunction

" Display the breakpoint source code in a window. The function is called after
" the <CR> key or the mouse is used in a '(clewn)_breakpoints' window.
"   'fname': the source code full path name.
"   'lnum':    the source code line number.
function pyclewn#buffers#GotoBreakpoint(fname, lnum)
    if exists("*Pyclewn_GotoBreakpoint")
        call Pyclewn_GotoBreakpoint(a:fname, a:lnum)
        return
    endif
    call s:split_source(a:fname, a:lnum)
endfunction

"-------------------   END AUTOLOAD FUNCTIONS   -------------------

" Split a window and display a buffer with previewheight.
function s:split_console(fname, location)
    if a:location == "none"
        return
    endif

    " The window does not exist.
    let l:nr = bufwinnr(a:fname)
    if l:nr == -1
        call s:split(a:fname, a:location)
    endif

    " Split the window (when the only window)
    " this is required to prevent Vim display toggling between
    " clewn console and the last buffer where the cursor was
    " positionned (clewn does not know that this buffer is not
    " anymore displayed).
    if winnr("$") == 1
        call s:split("", a:location)
    endif
endfunction

" Split a window and return to the initial window,
" if 'location' is not ''
"   'location' may be: '', 'top', 'bottom', 'left' or 'right'.
function s:split(fname, location)
    let nr = 1
    let l:split = "split"
    let spr = &splitright
    let sb = &splitbelow
    set nosplitright
    set nosplitbelow
    let prevbuf_winnr = bufwinnr(bufname("%"))
    if winnr("$") == 1 && (a:location == "right" || a:location == "left")
        let l:split = "vsplit"
        if a:location == "right"
            set splitright
        else
            let prevbuf_winnr = 2
        endif
    else
        if a:location == "bottom"
            let nr = winnr("$")
            set splitbelow
        else
            let prevbuf_winnr = prevbuf_winnr + 1
        endif
        if a:location != ""
            exe nr . "wincmd w"
        endif
    endif
    let nr = bufnr(a:fname)
    if nr != -1
        exe &previewheight . l:split
        exe nr . "buffer"
    else
        exe &previewheight . l:split . " " . a:fname
    endif
    let &splitright = spr
    let &splitbelow = sb
    exe prevbuf_winnr . "wincmd w"
endfunc

function s:split_source(fname, lnum)
    let l:nr = bufwinnr(a:fname)
    if l:nr != -1
        exe l:nr . "wincmd w"
        if a:lnum != ""
            call cursor(a:lnum, 0)
        endif
        return
    endif

    " Search for a source code window.
    let l:count = winnr('$')
    let l:nr = 1
    while l:nr <= l:count
        if ! s:is_clewn_buffer(bufname(winbufnr(l:nr)))
            exe l:nr . "wincmd w"
            break
        endif
        let l:nr = l:nr + 1
    endwhile

    " Split the window.
    exe &previewheight . "split"
    if l:nr > l:count
        wincmd w
    endif
    exe "edit " . a:fname
    if a:lnum != ""
        call cursor(a:lnum, 0)
    endif
endfunction

function s:is_clewn_buffer(fname)
    for l:name in ['console', 'variables', 'breakpoints', 'backtrace', 'threads']
        if a:fname == "(clewn)_" . l:name
            return 1
        endif
    endfor
    return 0
endfunction

