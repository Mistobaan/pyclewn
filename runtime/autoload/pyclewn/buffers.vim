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
    call s:winsplit("(clewn)_console", a:location)
endfunction

" Display the '(clewn)_variables' buffer in a window, split if needed. The
" function is called before the 'Cdbgvar' command is executed and after
" 'Pyclewn_DisplayConsole'.
function pyclewn#buffers#DbgvarSplit()
    if exists("*Pyclewn_DbgvarSplit")
        call Pyclewn_DbgvarSplit()
        return
    endif
    call s:winsplit("(clewn)_variables", "")
endfunction

" Display the '(clewn)_backtrace' buffer in a window. This is made necessary
" because the result of the <CR> key (or the mouse) may cause the
" '(clewn)_backtrace' window to be replaced by a source code window. The
" function is called after the <CR> key or the mouse is used in a
" '(clewn)_backtrace' window.
function pyclewn#buffers#BacktraceSplit()
    if exists("*Pyclewn_BacktraceSplit")
        call Pyclewn_BacktraceSplit()
        return
    endif
    call s:winsplit("(clewn)_backtrace", "")
endfunction

" Display the breakpoint source code in a window. The function is called after
" the <CR> key or the mouse is used in a '(clewn)_breakpoints' window.
"   'bufname': the source code full path name.
"   'lnum':    the source code line number.
function pyclewn#buffers#GotoBreakpoint(bufname, lnum)
    if exists("*Pyclewn_GotoBreakpoint")
        call Pyclewn_GotoBreakpoint(a:bufname, a:lnum)
        return
    endif

    let l:nr = bufwinnr(a:bufname)
    if l:nr == -1
        exe &previewheight . "split"
        wincmd w
        exe "edit " . a:bufname
    else
        exe l:nr . "wincmd w"
    endif
    call cursor(a:lnum, 0)
endfunction

"-------------------   END AUTOLOAD FUNCTIONS   -------------------

" Split a window and display a buffer with previewheight.
function s:winsplit(bufname, location)
    if a:location == "none"
        return
    endif

    " The window does not exist.
    let l:nr = bufwinnr(a:bufname)
    if l:nr == -1
        call s:split(a:bufname, a:location)
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
function s:split(bufname, location)
    let nr = 1
    let split = "split"
    let spr = &splitright
    let sb = &splitbelow
    set nosplitright
    set nosplitbelow
    let prevbuf_winnr = bufwinnr(bufname("%"))
    if winnr("$") == 1 && (a:location == "right" || a:location == "left")
	let split = "vsplit"
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
    let nr = bufnr(a:bufname)
    if nr != -1
        exe &previewheight . split
        exe nr . "buffer"
    else
        exe &previewheight . split . " " . a:bufname
    endif
    let &splitright = spr
    let &splitbelow = sb
    exe prevbuf_winnr . "wincmd w"
endfunc

