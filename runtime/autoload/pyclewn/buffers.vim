" vi:set ts=8 sts=4 sw=4 et tw=80:
" Pyclewn run time file.
" Maintainer:   <xdegaye at users dot sourceforge dot net>
"
" Manage pyclewn buffers.
"
if exists("s:did_buffers")
    finish
endif
let s:did_buffers = 1

"---------------------   AUTOLOAD FUNCTIONS   ---------------------

" Display one of the pyclewn buffers in a window. The function is triggered by a
" 'BufAdd' autocommand. The function is also called directly with 'name' as
" "(clewn)_console" just before the first 'C' command when the buffer list is
" empty (to workaround a problem with Vim that fails to send netbeans events
" when the buffer list is empty).
"   'name':     the pyclewn buffer name.
"   'location': the value of the '--window' option, i.e. "top", "bottom",
"               "left", "right" or "none".
function pyclewn#buffers#CreateWindow(name, location)
    if a:name == "(clewn)_empty"
        return
    endif
    if exists("*Pyclewn_CreateWindow")
        call Pyclewn_CreateWindow(a:name, a:location)
        return
    endif
    call s:create_window(a:name, a:location)
endfunction

" Display the '(clewn)_variables' buffer in a window, split if needed. The
" function is called before the 'Cdbgvar' command is executed.
function pyclewn#buffers#DbgvarSplit()
    if exists("*Pyclewn_DbgvarSplit")
        call Pyclewn_DbgvarSplit()
        return
    endif
    call s:split_clewnbuffer("(clewn)_variables", "")
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
"   'lnum':  the source code line number.
function pyclewn#buffers#GotoBreakpoint(fname, lnum)
    if exists("*Pyclewn_GotoBreakpoint")
        call Pyclewn_GotoBreakpoint(a:fname, a:lnum)
        return
    endif
    call s:split_source(a:fname, a:lnum)
endfunction

"-------------------   END AUTOLOAD FUNCTIONS   -------------------

" The '(clewn)_empty' buffer is used here to workaround the problem that
" BufWinLeave auto commands are never triggered when the clewn buffer is loaded
" in a window whose current buffer is a netbeans created file.
function s:create_window(name, location)
    if a:name == "(clewn)_console"
        " When the buffer list is empty, do not split the window.
        if bufname("%") == ""
            exe "edit (clewn)_empty"
        else
            call s:split_clewnbuffer(a:name, a:location)
        endif
        return
    endif

    if a:name == "(clewn)_variables" || a:location != "top"
        return
    endif

    " Search for any existing list buffer window.
    let l:list_buffers = {'breakpoints':1, 'backtrace':2, 'threads':3}
    let l:gotit = 0
    for l:buf in keys(l:list_buffers)
        let l:name = "(clewn)_" . l:buf
        let l:nr = bufwinnr(l:name)
        if l:nr != -1
            if l:name == a:name
                return
            endif
            let l:gotit = 1
        endif
        if l:name == a:name
            let l:bufnr = l:list_buffers[l:buf]
        endif
    endfor

    let l:prevbuf_winnr = bufwinnr(bufname("%"))
    let l:count = 0
    if bufwinnr("(clewn)_console") == 1
        let l:count = 1
    endif

    if ! l:gotit
        " Create the 3 windows on the first BufAdd event of a list buffer.
        wincmd w
        if l:count
            exe (&previewheight - 4) . "split"
            wincmd w
        else
            4split
        endif
        exe "edit (clewn)_empty"
        vsplit | vsplit
    endif

    " Edit the new buffer.
    let l:bufnr = l:bufnr + l:count
    exe l:bufnr . "wincmd w"
    exe "edit " . a:name
    setlocal nowrap

    exe l:prevbuf_winnr . "wincmd w"
endfunction

" Split a window and display a buffer with previewheight.
function s:split_clewnbuffer(fname, location)
    if a:location == "none"
        return
    endif

    " The window does not exist.
    let l:nr = bufwinnr(a:fname)
    if l:nr == -1
        call s:split_location(a:fname, a:location)
    endif

    " Split the window (when the only window) this is required to prevent Vim
    " display toggling between clewn console and the last buffer where the
    " cursor was positionned (clewn does not know that this buffer is not
    " anymore displayed).
    if winnr("$") == 1
        call s:split_location("", a:location)
    endif
endfunction

" Split a window and return to the initial window,
" if 'location' is not ''
"   'location' may be: '', 'top', 'bottom', 'left' or 'right'.
function s:split_location(fname, location)
    let l:nr = 1
    let l:split = "split"
    let l:spr = &splitright
    let l:sb = &splitbelow
    set nosplitright
    set nosplitbelow
    let l:prevbuf_winnr = bufwinnr(bufname("%"))
    if winnr("$") == 1 && (a:location == "right" || a:location == "left")
        let l:split = "vsplit"
        if a:location == "right"
            set splitright
        else
            let l:prevbuf_winnr = 2
        endif
    else
        if a:location == "bottom"
            let l:nr = winnr("$")
            set splitbelow
        else
            let l:prevbuf_winnr = l:prevbuf_winnr + 1
        endif
        if a:location != ""
            exe l:nr . "wincmd w"
        endif
    endif
    let l:nr = bufnr(a:fname)
    if l:nr != -1
        exe &previewheight . l:split
        exe l:nr . "buffer"
        setlocal nowrap
    else
        exe &previewheight . l:split . " " . a:fname
        setlocal nowrap
    endif
    let &splitright = l:spr
    let &splitbelow = l:sb
    exe l:prevbuf_winnr . "wincmd w"
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
        if bufname(winbufnr(l:nr)) !~# "^(clewn)_"
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

