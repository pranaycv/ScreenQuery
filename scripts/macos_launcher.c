/* ScreenQuery.app main executable.

   Stays a Mach-O inside the bundle (so Launch Services keeps this process as
   ScreenQuery) and runs the repo's virtualenv in-process. A shell script that
   execs .venv/bin/python is replaced by Command Line Tools Python.app, and
   macOS then treats the app as com.apple.python3 — no ScreenQuery status item,
   and a later double-click does nothing visible.

   Failures are appended to ~/Library/Logs/ScreenQuery.log and shown in a dialog.
*/
#include <CoreFoundation/CoreFoundation.h>
#include <Python.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#define REPO "/Users/pranay/ScreenQuery/screenquery"
#define PY_HOME "/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9"
#define VENV_SITE REPO "/.venv/lib/python3.9/site-packages"
#define REPO_LITERAL "\"" REPO "\""
#define SITE_LITERAL "\"" VENV_SITE "\""

static char log_path[1024];

static void prepare_log_path(void) {
    const char *home = getenv("HOME");
    if (home && home[0]) {
        snprintf(log_path, sizeof log_path, "%s/Library/Logs/ScreenQuery.log", home);
    } else {
        snprintf(log_path, sizeof log_path, "/tmp/ScreenQuery.log");
    }
}

static void log_line(const char *text) {
    FILE *file = fopen(log_path, "a");
    if (!file) {
        return;
    }
    time_t now = time(NULL);
    struct tm local;
    localtime_r(&now, &local);
    char stamp[64];
    strftime(stamp, sizeof stamp, "%Y-%m-%d %H:%M:%S", &local);
    fprintf(file, "%s %s\n", stamp, text);
    fclose(file);
}

static void attach_log(void) {
    int fd = open(log_path, O_WRONLY | O_CREAT | O_APPEND, 0644);
    if (fd < 0) {
        return;
    }
    dup2(fd, STDOUT_FILENO);
    dup2(fd, STDERR_FILENO);
    if (fd > 2) {
        close(fd);
    }
}

static void alert(const char *message) {
    CFStringRef body = CFStringCreateWithCString(NULL, message, kCFStringEncodingUTF8);
    if (!body) {
        return;
    }
    CFUserNotificationDisplayAlert(
        0,
        kCFUserNotificationStopAlertLevel,
        NULL,
        NULL,
        NULL,
        CFSTR("ScreenQuery"),
        body,
        CFSTR("OK"),
        NULL,
        NULL,
        NULL);
    CFRelease(body);
}

static int fail(const char *message) {
    log_line(message);
    alert(message);
    return 1;
}

static int run_screenquery(void) {
    static const char *bootstrap =
        "import os, sys, site\n"
        "repo = " REPO_LITERAL "\n"
        "os.chdir(repo)\n"
        "if repo not in sys.path:\n"
        "    sys.path.insert(0, repo)\n"
        "site.addsitedir(" SITE_LITERAL ")\n"
        "sys.argv = ['screenquery']\n"
        "import runpy\n"
        "runpy.run_module('screenquery', run_name='__main__', alter_sys=True)\n";

    PyObject *main_mod = PyImport_AddModule("__main__");
    if (!main_mod) {
        return fail("ScreenQuery could not start Python. See ~/Library/Logs/ScreenQuery.log");
    }
    PyObject *globals = PyModule_GetDict(main_mod);
    PyObject *result = PyRun_String(bootstrap, Py_file_input, globals, globals);
    if (!result) {
        if (PyErr_ExceptionMatches(PyExc_SystemExit)) {
            PyErr_Clear();
            return 0;
        }
        PyErr_Print();
        PyErr_Clear();
        return fail("ScreenQuery could not start. See ~/Library/Logs/ScreenQuery.log");
    }
    Py_DECREF(result);
    return 0;
}

int main(void) {
    prepare_log_path();
    log_line("launch");
    attach_log();

    if (chdir(REPO) != 0) {
        char message[256];
        snprintf(message, sizeof message, "ScreenQuery could not open %s (%s).", REPO, strerror(errno));
        return fail(message);
    }
    if (access(VENV_SITE, R_OK) != 0) {
        return fail("ScreenQuery could not find its virtualenv. See ~/Library/Logs/ScreenQuery.log");
    }

    wchar_t *home = Py_DecodeLocale(PY_HOME, NULL);
    if (!home) {
        return fail("ScreenQuery could not locate Python. See ~/Library/Logs/ScreenQuery.log");
    }
    Py_SetPythonHome(home);
    Py_Initialize();
    if (!Py_IsInitialized()) {
        PyMem_RawFree(home);
        return fail("ScreenQuery could not start Python. See ~/Library/Logs/ScreenQuery.log");
    }

    int code = run_screenquery();
    if (Py_FinalizeEx() < 0 && code == 0) {
        code = 1;
    }
    PyMem_RawFree(home);
    return code;
}
