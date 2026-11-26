// Exécutable de ClipRoll.app (DMG signé) : lance Resources/bootstrap.sh.
// Un vrai binaire (et non un script) pour que la signature Developer ID + runtime renforcé + notarisation s'appliquent.
#include <libgen.h>
#include <limits.h>
#include <mach-o/dyld.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

int main(void) {
    char exe[PATH_MAX], real[PATH_MAX], script[PATH_MAX];
    uint32_t size = sizeof(exe);
    if (_NSGetExecutablePath(exe, &size) != 0 || !realpath(exe, real)) return 1;
    char *macos = dirname(real);                 // .../ClipRoll.app/Contents/MacOS
    snprintf(script, sizeof(script), "%s/../Resources/bootstrap.sh", macos);
    char *argv[] = {"/bin/bash", script, NULL};
    execv("/bin/bash", argv);
    perror("ClipRoll");
    return 1;
}
