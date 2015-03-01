" A function to test the ':Pyclewn' command in a script.
function PyclewnScripting(cmd)
    if has("netbeans_enabled")
        echohl ErrorMsg
        echo "Error: netbeans is already connected."
        call inputsave()
        call input("Press the <Enter> key to continue.")
        call inputrestore()
        echohl None
        return
    endif

    let g:pyclewn_args="--gdb=async --level=nbdebug --file=logfile"
    Pyclewn gdb
    Cfile testsuite/foobar
    exe a:cmd
endfunc

