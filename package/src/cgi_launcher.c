/* Copyright (c) 2026 AWA <https://www.akkdiy.cn>. All rights reserved. */
#define _GNU_SOURCE
#include <dirent.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#ifndef DBBACKUP_ENTRY
#error DBBACKUP_ENTRY must be index or api
#endif

extern char **environ;

static const char *const allowed_env[] = {
    "GATEWAY_INTERFACE", "REQUEST_METHOD", "QUERY_STRING", "CONTENT_LENGTH",
    "CONTENT_TYPE", "HTTP_COOKIE", "HTTP_HOST", "HTTP_ORIGIN", "HTTP_REFERER",
    "HTTP_ACCEPT", "HTTP_ACCEPT_LANGUAGE", "HTTP_X_CSRF_TOKEN",
    "AUTH_TYPE", "DOCUMENT_ROOT", "PATH_INFO", "PATH_TRANSLATED", "REMOTE_ADDR", "REMOTE_HOST", "REMOTE_PORT", "REMOTE_USER", "REQUEST_SCHEME", "SERVER_ADDR", "SERVER_NAME", "SERVER_PORT", "SERVER_PROTOCOL", "SERVER_SOFTWARE", "SCRIPT_URI", "SCRIPT_URL",
    "HTTPS", "SCRIPT_NAME", "SCRIPT_FILENAME", "REQUEST_URI", "REDIRECT_STATUS",
    NULL
};

static int is_allowed(const char *entry)
{
    size_t i;
    const char *eq = strchr(entry, '=');
    size_t n = eq ? (size_t)(eq - entry) : strlen(entry);
    if (n > 5 && strncmp(entry, "HTTP_", 5) == 0) {
        if (n == 10 && strncmp(entry, "HTTP_PROXY", n) == 0)
            return 0;
        return 1;
    }
    for (i = 0; allowed_env[i]; ++i) {
        if (strlen(allowed_env[i]) == n && strncmp(entry, allowed_env[i], n) == 0)
            return 1;
    }
    return 0;
}

static int is_python3_name(const char *name)
{
    size_t i;
    if (strncmp(name, "python3", 7) != 0)
        return 0;
    if (name[7] == '\0')
        return 1;
    if (name[7] != '.' || name[8] < '0' || name[8] > '9')
        return 0;
    for (i = 8; name[i]; ++i) {
        if (name[i] != '.' && (name[i] < '0' || name[i] > '9'))
            return 0;
    }
    return name[i - 1] != '.';
}

static const char *find_packaged_python(void)
{
    DIR *packages = opendir("/var/packages");
    struct dirent *package;
    static char best[4096];
    size_t best_score = 0;
    if (!packages)
        return NULL;
    while ((package = readdir(packages)) != NULL) {
        const char *name = package->d_name;
        const char *bin_dirs[] = {"usr/local/bin", "usr/bin", NULL};
        size_t b;
        if (strncmp(name, "Python3", 7) != 0)
            continue;
        for (b = 0; bin_dirs[b]; ++b) {
            char directory[4096];
            int n = snprintf(directory, sizeof(directory),
                             "/var/packages/%s/target/%s", name, bin_dirs[b]);
            DIR *bin;
            struct dirent *candidate;
            if (n < 0 || (size_t)n >= sizeof(directory))
                continue;
            bin = opendir(directory);
            if (!bin)
                continue;
            while ((candidate = readdir(bin)) != NULL) {
                char path[4096];
                size_t score;
                n = snprintf(path, sizeof(path), "%s/%s", directory,
                             candidate->d_name);
                if (n < 0 || (size_t)n >= sizeof(path) ||
                    !is_python3_name(candidate->d_name) || access(path, X_OK) != 0)
                    continue;
                score = strlen(candidate->d_name);
                if (score <= best_score)
                    continue;
                memcpy(best, path, (size_t)n + 1);
                best_score = score;
            }
            closedir(bin);
        }
    }
    closedir(packages);
    return best_score ? best : NULL;
}

int main(void)
{
    char **envp;
    size_t count = 0, i, out = 0;
    const char *python_candidates[] = {
        "/var/packages/Python3/target/usr/local/bin/python3",
        "/var/packages/Python3/target/usr/bin/python3",
        "/usr/local/bin/python3",
        "/usr/bin/python3",
        NULL
    };
    const char *python = find_packaged_python();
    const char *script = "/var/packages/DBBackup/target/share/cgi_app.py";
    char *argv[] = {NULL, (char *)script, (char *)DBBACKUP_ENTRY, NULL};

    for (i = 0; !python && python_candidates[i]; ++i) {
        if (access(python_candidates[i], X_OK) == 0) {
            python = python_candidates[i];
            break;
        }
    }
    if (!python) {
        fputs("Status: 503 Service Unavailable\r\nContent-Type: text/plain; charset=utf-8\r\n\r\nPython 3 runtime unavailable.\n", stdout);
        return 0;
    }

    while (environ[count]) ++count;
    envp = calloc(count + 3, sizeof(char *));
    if (!envp) {
        fputs("Status: 500 Internal Server Error\r\nContent-Type: text/plain; charset=utf-8\r\n\r\nInternal error.\n", stdout);
        return 0;
    }
    umask(077);
    envp[out++] = "PATH=/usr/local/bin:/usr/bin:/bin";
    envp[out++] = "PYTHONNOUSERSITE=1";
    for (i = 0; i < count; ++i) {
        if (is_allowed(environ[i])) envp[out++] = environ[i];
    }
    envp[out] = NULL;
    argv[0] = (char *)python;
    execve(python, argv, envp);
    fprintf(stdout, "Status: 503 Service Unavailable\r\nContent-Type: text/plain; charset=utf-8\r\n\r\nUnable to start backend (%d).\n", errno);
    return 0;
}

