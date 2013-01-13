/* The C implementation of the Tracer class in the bdb module. */

#include "Python.h"
#include "structmember.h"
#include "frameobject.h"

typedef struct {
    PyObject_HEAD

    /* Attributes */
    PyObject *trace_dispatch;
    PyObject *breakpoints;
    PyObject *botframe;
    PyObject *quitting;
    PyObject *topframe;
    PyObject *topframe_locals;
    PyObject *stopframe;
    PyObject *stop_lineno;
    PyObject *skip_modules;
    PyObject *skip_calls;
    PyObject *linenumbers;      /* The list of cached line number objects.
                                 * Using this cache gives a 3-5 %
                                 * performance gain.*/

    /* Internals */
    int ignore_first_call_event;
    PyObject *lcfilename_cache; /* Dictionary mapping a co_filename object
                                 * to its co_filename.lower() object. */

    /* The following three references are used to avoid a call to bkpt_in_code
     * when tracing lines in the same function (a performance gain of 14-28 %).
     * The bdb Python module must make sure not to invalidate the module_bps
     * and code_bps references when those dictionaries become empty ! */
    PyObject *module_bps;       /* The current module_bps object. */
    PyObject *code_bps;         /* The current code_bps object. */
    PyCodeObject *f_code;       /* The current f_code object. */
} BdbTracer;

static PyMemberDef
BdbTracer_members[] = {
    {"trace_dispatch", T_OBJECT, offsetof(BdbTracer, trace_dispatch), 0,
        PyDoc_STR("This is self, the trace object.")},
    {"breakpoints", T_OBJECT, offsetof(BdbTracer, breakpoints), 0,
        PyDoc_STR("A dictionary mapping filenames to a ModuleBreakpoints"
                  " instances.")},
    {"botframe", T_OBJECT, offsetof(BdbTracer, botframe), 0,
        PyDoc_STR("The oldest frame.")},
    {"quitting", T_OBJECT, offsetof(BdbTracer, quitting), 0,
        PyDoc_STR("Quit the debugging session when True.")},
    {"topframe", T_OBJECT, offsetof(BdbTracer, topframe), 0,
        PyDoc_STR("The current frame.")},
    {"topframe_locals", T_OBJECT, offsetof(BdbTracer, topframe_locals), 0,
        PyDoc_STR("The f_locals dictionary.")},
    {"stopframe", T_OBJECT, offsetof(BdbTracer, stopframe), 0, NULL},
    {"stop_lineno", T_OBJECT, offsetof(BdbTracer, stop_lineno), 0, NULL},
    {"skip_modules", T_OBJECT, offsetof(BdbTracer, skip_modules), 0, NULL},
    {"skip_calls", T_OBJECT, offsetof(BdbTracer, skip_calls), 0, NULL},
    {"linenumbers", T_OBJECT, offsetof(BdbTracer, linenumbers), 0, NULL},
    {NULL}
};

static int
BdbTracer_init(BdbTracer *self, PyObject *args, PyObject *kwds)
{
    static char *kwlist[] = {"to_lowercase",
                             "skip_modules", "skip_calls", NULL};
    PyObject *lowercase;
    PyObject *result;

    self->trace_dispatch = NULL;
    self->breakpoints = NULL;
    self->botframe = NULL;
    self->quitting = NULL;
    self->topframe = NULL;
    self->topframe_locals = NULL;
    self->stopframe = NULL;
    self->stop_lineno = NULL;
    self->skip_modules = NULL;
    self->skip_calls = NULL;
    self->linenumbers = NULL;
    self->module_bps = NULL;
    self->code_bps = NULL;
    self->f_code = NULL;
    self->lcfilename_cache = NULL;

    if (! PyArg_ParseTupleAndKeywords(args, kwds, "O!|O!O!:init", kwlist,
            &PyBool_Type, &lowercase,
            &PyTuple_Type, &self->skip_modules,
            &PyTuple_Type, &self->skip_calls))
        return -1;

    Py_INCREF(self);
    self->trace_dispatch = (PyObject *)self;

    if (lowercase == Py_True) {
        self->lcfilename_cache = PyDict_New();
        if (self->lcfilename_cache == NULL)
            goto fail;
    }

    if (self->skip_modules == NULL) {
        self->skip_modules = Py_BuildValue("()");
        if (self->skip_modules == NULL)
            goto fail;
    }
    else
        Py_INCREF(self->skip_modules);

    if (self->skip_calls == NULL) {
        self->skip_calls = Py_BuildValue("()");
        if (self->skip_calls == NULL)
            goto fail;
    }
    else
        Py_INCREF(self->skip_calls);

    self->breakpoints = PyDict_New();
    if (self->breakpoints == NULL)
        goto fail;

    self->linenumbers = PyList_New(0);
    if (self->linenumbers == NULL)
        goto fail;

    result = PyObject_CallMethod((PyObject *)self, "reset", NULL);
    if (result == NULL)
        goto fail;
    Py_DECREF(result);

    return 0;

fail:
    Py_XDECREF(self->trace_dispatch);
    Py_XDECREF(self->skip_modules);
    Py_XDECREF(self->skip_calls);
    Py_XDECREF(self->breakpoints);
    Py_XDECREF(self->linenumbers);
    Py_XDECREF(self->lcfilename_cache);
    return -1;
}

static void
BdbTracer_dealloc(BdbTracer *self)
{
    Py_XDECREF(self->trace_dispatch);
    Py_XDECREF(self->breakpoints);
    Py_XDECREF(self->botframe);
    Py_XDECREF(self->quitting);
    Py_XDECREF(self->topframe);
    Py_XDECREF(self->topframe_locals);
    Py_XDECREF(self->stopframe);
    Py_XDECREF(self->stop_lineno);
    Py_XDECREF(self->skip_modules);
    Py_XDECREF(self->skip_calls);
    Py_XDECREF(self->linenumbers);
    Py_XDECREF(self->module_bps);
    Py_XDECREF(self->code_bps);
    Py_XDECREF(self->f_code);
    Py_XDECREF(self->lcfilename_cache);
    Py_TYPE(self)->tp_free((PyObject*)self);
}

static int
stop_here(BdbTracer *self, PyFrameObject *frame)
{
    PyObject *result;
    int lineno;

    if (PyTuple_GET_SIZE(self->skip_modules)) {
        result = PyObject_CallMethod((PyObject *)self, "is_skipped_module",
                                     "(O)", frame);
        if (result == NULL)
            return -1;
        if (PyObject_IsTrue(result)) {
            Py_DECREF(result);
            return 0;
        }
        Py_DECREF(result);
    }

    lineno = PyLong_AsLong(self->stop_lineno);
    if (lineno == -1 && PyErr_Occurred())
        return -1;

    if ((PyObject *)frame == self->stopframe || self->stopframe == Py_None) {
        if (lineno == -1)
            return 0;
        return frame->f_lineno >= lineno;
    }

    return 0;
}

static PyObject *
bkpt_in_code(BdbTracer *self, PyFrameObject *frame)
{
    PyObject *filename = frame->f_code->co_filename;
    PyObject *result = NULL;
    PyObject *lc_filename = NULL;
    PyObject *firstlineno;
    PyObject *module_bps;
    PyObject *code_bps;

    if (self->lcfilename_cache != NULL) {
        lc_filename = PyDict_GetItem(self->lcfilename_cache, filename);
        if (lc_filename == NULL) {
            lc_filename = PyObject_CallMethod(filename, "lower", NULL);
            if (lc_filename == NULL)
                return NULL;
            if (PyDict_SetItem(self->lcfilename_cache, filename, lc_filename)){
                Py_DECREF(lc_filename);
                return NULL;
            }
        }
        else
            Py_INCREF(lc_filename);
        filename = lc_filename;
    }

    module_bps = PyDict_GetItem(self->breakpoints, filename);
    if (module_bps != NULL && frame->f_code->co_firstlineno <
            PyList_GET_SIZE(self->linenumbers)) {
        firstlineno = PyList_GET_ITEM(self->linenumbers,
                                      frame->f_code->co_firstlineno);
        if (firstlineno != Py_None) {
            code_bps = PyDict_GetItem(module_bps, firstlineno);
            if (code_bps != NULL) {
                Py_INCREF(module_bps);
                Py_XDECREF(self->module_bps);
                self->module_bps = module_bps;

                Py_INCREF(code_bps);
                Py_XDECREF(self->code_bps);
                self->code_bps = code_bps;

                Py_INCREF(frame->f_code);
                Py_XDECREF(self->f_code);
                self->f_code = frame->f_code;

                Py_INCREF(module_bps);
                result = module_bps;
                goto fin;
            }
        }
    }

    Py_INCREF(Py_None);
    result = Py_None;

fin:
    Py_XDECREF(lc_filename);
    return result;
}

static PyObject *
bkpt_at_line(BdbTracer *self, PyFrameObject *frame)
{
    PyObject *result = NULL;
    PyObject *module_bps;
    PyObject *lineno;
    int haskey;

    if (frame->f_code == self->f_code) {
        module_bps = self->module_bps;
        Py_INCREF(module_bps);
    }
    else {
        module_bps = bkpt_in_code(self, frame);
        if (module_bps == NULL)
            return NULL;
        else if (module_bps == Py_None)
            return Py_None;
    }

    if (frame->f_lineno < PyList_GET_SIZE(self->linenumbers)) {
        lineno = PyList_GET_ITEM(self->linenumbers, frame->f_lineno);
        if (lineno != Py_None) {
            haskey = PyDict_Contains(self->code_bps, lineno);
            if (haskey == -1)
                goto fin;
            else if (haskey)
                return module_bps;
        }
    }

    Py_INCREF(Py_None);
    result = Py_None;

fin:
    Py_DECREF(module_bps);
    return result;
}

static PyObject *
user_method(BdbTracer *self, PyFrameObject *frame, char *name, PyObject *arg)
{
    PyObject *result;
    PyObject *tmp;

    if (self->botframe == Py_None) {
        Py_INCREF(frame);
        self->botframe = (PyObject *)frame;
        Py_DECREF(Py_None);
    }

    tmp = self->topframe;
    Py_INCREF(frame);
    self->topframe = (PyObject *)frame;
    Py_DECREF(tmp);

    tmp = self->topframe_locals;
    Py_INCREF(Py_None);
    self->topframe_locals = Py_None;
    Py_DECREF(tmp);

    /* call the Python-level function */
    PyFrame_FastToLocals(frame);
    if (strcmp(name, "user_line") == 0)
        result = PyObject_CallMethod((PyObject *)self, name, "(O)", frame);
    else
        result = PyObject_CallMethod((PyObject *)self, name, "OO", frame, arg);
    PyFrame_LocalsToFast(frame, 1);

    if (result == NULL)
        return NULL;
    Py_DECREF(result);

    tmp = self->topframe;
    Py_INCREF(Py_None);
    self->topframe = Py_None;
    Py_DECREF(tmp);

    tmp = self->topframe_locals;
    Py_INCREF(Py_None);
    self->topframe_locals = Py_None;
    Py_DECREF(tmp);

    return PyObject_CallMethod((PyObject *)self, "get_traceobj", NULL);
}

static int
tracer(PyObject *traceobj, PyFrameObject *frame, int what, PyObject *arg)
{
    BdbTracer *self = (BdbTracer *)traceobj;
    PyObject *module_bps;
    PyFrameObject *f_back;
    PyObject *result;
    PyObject *tmp;
    int lineno;
    int rc;

    if(what != PyTrace_CALL && frame->f_trace == NULL)
        return 0;

    /* One case where arg is NULL is at the return event that follows an
     * exception event. */
    if (arg == NULL)
        arg = Py_None;

    /* A LINE event. */
    if (what == PyTrace_LINE) {
        rc = stop_here(self, frame);
        if (rc == -1)
            goto fail;
        else if (rc) {
            result = user_method(self, frame, "user_line", NULL);
            goto fin;
        }

        module_bps = bkpt_at_line(self, frame);
        if (module_bps == NULL)
            goto fail;
        else if (module_bps == Py_None)
            Py_DECREF(Py_None);
        else {
            result = user_method(self, frame, "bkpt_user_line", module_bps);
            Py_DECREF(module_bps);
            goto fin;
        }
    }

    /* A CALL event. */
    else if (what == PyTrace_CALL) {
        if (self->ignore_first_call_event) {
            self->ignore_first_call_event = 0;
            Py_INCREF(self);
            result = (PyObject *)self;
            goto fin;
        }

        rc = PySequence_Contains(self->skip_calls, (PyObject *)frame->f_code);
        if (rc == -1)
            goto fail;
        else if (rc) {
            Py_INCREF(Py_None);
            result = Py_None;
            goto fin;
        }

        rc = stop_here(self, frame);
        if (rc == -1)
            goto fail;
        result = bkpt_in_code(self, frame);
        if (result == NULL)
            goto fail;
        if (! rc && result == Py_None)
            goto fin;
        Py_DECREF(result);
        if (rc) {
            result = user_method(self, frame, "user_call", arg);
            goto fin;
        }
    }

    /* A RETURN event. */
    else if (what == PyTrace_RETURN) {
        rc = stop_here(self, frame);
        if (rc == -1)
            goto fail;
        if (rc || (PyObject *)frame == self->stopframe) {
            result = user_method(self, frame, "user_return", arg);
            if (result == NULL)
                goto fail;
            else if (result == Py_None)
                goto fin;
            Py_DECREF(result);

            lineno = PyLong_AsLong(self->stop_lineno);
            if (lineno == -1 && PyErr_Occurred())
                goto fail;
            if ((PyObject *)frame != self->botframe &&
                    ((self->stopframe == Py_None && lineno == 0) ||
                    (PyObject *)frame == self->stopframe)) {
                f_back = frame->f_back;
                if (f_back != NULL && f_back->f_trace == NULL) {
                    Py_INCREF(self);
                    /* f_lineno must be accurate when f_trace is set. */
                    f_back->f_lineno = PyFrame_GetLineNumber(f_back);
                    f_back->f_trace = (PyObject *)self;
                }

                tmp = self->stopframe;
                Py_INCREF(Py_None);
                self->stopframe = Py_None;
                Py_DECREF(tmp);

                tmp = self->stop_lineno;
                self->stop_lineno = PyLong_FromLong(0L);
                Py_DECREF(tmp);

            }
        }

        if ((PyObject *)frame == self->botframe) {
            result = PyObject_CallMethod((PyObject *)self,
                                         "stop_tracing", "(O)", frame);
            if (result == NULL)
                goto fail;
            Py_DECREF(result);
            Py_INCREF(Py_None);
            result = Py_None;
            goto fin;
        }
    }

    /* An EXCEPTION event. */
    else if (what == PyTrace_EXCEPTION) {
        rc = stop_here(self, frame);
        if (rc == -1)
            goto fail;
        else if (rc) {
            result = user_method(self, frame, "user_exception", arg);
            goto fin;
        }
    }

    Py_INCREF(self);
    result = (PyObject *)self;

fin:
    if (result == NULL)
        goto fail;
    if (result != Py_None) {
        tmp = frame->f_trace;
        frame->f_trace = NULL;
        Py_XDECREF(tmp);
        frame->f_trace = result;
    }
    else
        Py_DECREF(result);
    return 0;

fail:
    PyTraceBack_Here(frame);
    PyEval_SetTrace(NULL, NULL);
    Py_XDECREF(frame->f_trace);
    frame->f_trace = NULL;
    return -1;
}

static PyObject *
BdbTracer_reset(BdbTracer *self, PyObject *args, PyObject *kwds)
{
    static char *kwlist[] = {"ignore_first_call_event", "botframe", NULL};
    PyObject *ignore = NULL;
    PyObject *botframe = NULL;
    PyObject *tmp;

    if (! PyArg_ParseTupleAndKeywords(args, kwds, "|O!O:reset", kwlist,
            &PyBool_Type, &ignore, &botframe))
        return NULL;

    self->ignore_first_call_event = 1 ? ignore != Py_False : 0;

    tmp = self->botframe;
    if (botframe == NULL)
        self->botframe = Py_None;
    else
        self->botframe = botframe;
    Py_INCREF(self->botframe);
    Py_XDECREF(tmp);

    tmp = self->quitting;
    Py_INCREF(Py_False);
    self->quitting = Py_False;
    Py_XDECREF(tmp);

    tmp = self->topframe;
    Py_INCREF(Py_None);
    self->topframe = Py_None;
    Py_XDECREF(tmp);

    tmp = self->topframe_locals;
    Py_INCREF(Py_None);
    self->topframe_locals = Py_None;
    Py_XDECREF(tmp);

    tmp = self->stopframe;
    Py_INCREF(Py_None);
    self->stopframe = Py_None;
    Py_XDECREF(tmp);

    tmp = self->stop_lineno;
    self->stop_lineno = PyLong_FromLong(0L);
    Py_XDECREF(tmp);

    Py_RETURN_NONE;
}

static PyObject *
BdbTracer_stop_here(BdbTracer *self, PyObject *args)
{
    PyFrameObject *frame;
    int rc;

    if (! PyArg_ParseTuple(args, "O!", &PyFrame_Type, &frame))
        return NULL;

    rc = stop_here(self, frame);

    if (rc == -1)
        return NULL;
    else if (rc)
        Py_RETURN_TRUE;
    Py_RETURN_FALSE;
}

static PyObject *
BdbTracer_set_trace_dispatch(BdbTracer *self)
{
    PyEval_SetTrace(tracer, (PyObject *)self);
    Py_INCREF(Py_None);
    return Py_None;
}

static PyObject *
BdbTracer_stop_tracing(BdbTracer *self) {
    Py_INCREF(Py_NotImplemented);
    return Py_NotImplemented;
}

static PyObject *
BdbTracer_is_skipped_module(BdbTracer *self, PyObject *args)
{
    Py_INCREF(Py_NotImplemented);
    return Py_NotImplemented;
}

static PyObject *
BdbTracer_get_traceobj(BdbTracer *self) {
    Py_INCREF(Py_NotImplemented);
    return Py_NotImplemented;
}

static PyMethodDef BdbTracer_methods[] = {
    {"reset", (PyCFunction)BdbTracer_reset, METH_VARARGS | METH_KEYWORDS,
            NULL},
    {"stop_here", (PyCFunction)BdbTracer_stop_here, METH_VARARGS, NULL},
    {"set_trace_dispatch", (PyCFunction)BdbTracer_set_trace_dispatch,
            METH_NOARGS, NULL},
    {"stop_tracing", (PyCFunction)BdbTracer_stop_tracing,
            METH_VARARGS | METH_KEYWORDS, PyDoc_STR("Method overriden.")},
    {"is_skipped_module", (PyCFunction)BdbTracer_is_skipped_module,
            METH_VARARGS, PyDoc_STR("Method overriden by Bdb.")},
    {"get_traceobj", (PyCFunction)BdbTracer_get_traceobj, METH_NOARGS,
            PyDoc_STR("Method overriden by Bdb.")},
    {NULL, NULL} /* sentinel */
};

static PyTypeObject BdbTracer_Type = {
    PyVarObject_HEAD_INIT(NULL, 0)
    "_bdb.BdbTracer",               /*tp_name*/
    sizeof(BdbTracer),              /*tp_basicsize*/
    0,                              /*tp_itemsize*/
    (destructor)BdbTracer_dealloc,  /*tp_dealloc*/
    0,                              /*tp_print*/
    0,                              /*tp_getattr*/
    0,                              /*tp_setattr*/
    0,                              /*tp_reserved*/
    0,                              /*tp_repr*/
    0,                              /*tp_as_number*/
    0,                              /*tp_as_sequence*/
    0,                              /*tp_as_mapping*/
    0,                              /*tp_hash*/
    0,                              /*tp_call*/
    0,                              /*tp_str*/
    0,                              /*tp_getattro*/
    0,                              /*tp_setattro*/
    0,                              /*tp_as_buffer*/
    Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE, /*tp_flags*/
    "The C bdb tracer.",            /*tp_doc*/
    0,                              /*tp_traverse*/
    0,                              /*tp_clear*/
    0,                              /*tp_richcompare*/
    0,                              /*tp_weaklistoffset*/
    0,                              /*tp_iter*/
    0,                              /*tp_iternext*/
    BdbTracer_methods,              /*tp_methods*/
    BdbTracer_members,              /*tp_members*/
    0,                              /*tp_getset*/
    0,                              /*tp_base*/
    0,                              /*tp_dict*/
    0,                              /*tp_descr_get*/
    0,                              /*tp_descr_set*/
    0,                              /*tp_dictoffset*/
    (initproc)BdbTracer_init,       /*tp_init*/
    0,                              /*tp_alloc*/
    0,                              /*tp_new*/
    0,                              /*tp_free*/
    0,                              /*tp_is_gc*/
};

PyDoc_STRVAR(module_doc, "The _bdb module.");

static struct PyModuleDef _bdbmodule = {
    PyModuleDef_HEAD_INIT,
    "_bdb",
    module_doc,
    -1,
    NULL, NULL, NULL, NULL, NULL
};

/* Initialization function for the module (*must* be called PyInit__bdb). */
PyMODINIT_FUNC
PyInit__bdb(void)
{
    PyObject *m = NULL;

    BdbTracer_Type.tp_new = PyType_GenericNew;
    if (PyType_Ready(&BdbTracer_Type) < 0)
        return NULL;

    m = PyModule_Create(&_bdbmodule);
    if (m == NULL)
        return NULL;

    Py_INCREF(&BdbTracer_Type);
    PyModule_AddObject(m, "BdbTracer", (PyObject *)&BdbTracer_Type);
    return m;
}

