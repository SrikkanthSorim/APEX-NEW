# APEX backend container image.
#
# Deployed on Render's *Docker* runtime rather than its native Python runtime,
# because this service shells out to real binaries that the Python runtime does
# not provide:
#   * git    -- app/infrastructure/git/git_command_runner.py (Discovery clones)
#   * java   -- app/infrastructure/java_runtime.py
#   * mvn    -- app/infrastructure/migration_engine/automated_migration_runner.py
#   * gradle -- ditto
#
# The React frontend is NOT bundled here; it is deployed separately as a Render
# Static Site and talks to this service cross-origin (see VITE_API_URL there and
# CORS_ORIGINS here).

FROM python:3.12-slim-bookworm

# -- OS packages ------------------------------------------------------------ #
# git is non-negotiable: Discovery cannot clone a repository without it.
# curl/unzip are only needed to fetch the Java toolchain below.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        git \
        curl \
        unzip \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# -- Java toolchain --------------------------------------------------------- #
# Installed under /opt/java/jdk-<major>, which matters: _discover_jdks()
# (app/infrastructure/java_runtime.py) scans _POSIX_JDK_SEARCH_ROOTS -- which
# includes "/opt/java" -- and infers the major version from the DIRECTORY NAME
# via _infer_major_from_name(). So "jdk-17" / "jdk-21" are what make both JDKs
# discoverable; renaming these directories silently breaks version selection.
#
# Two JDKs are installed so _select_jdk_for_target() can compile to either 17 or
# 21 (a JDK can target any older --release, never a newer one).
ARG JDK_VERSIONS="17 21"
RUN set -eux; \
    mkdir -p /opt/java; \
    for major in ${JDK_VERSIONS}; do \
        curl -fsSL -o /tmp/jdk.tar.gz \
            "https://api.adoptium.net/v3/binary/latest/${major}/ga/linux/x64/jdk/hotspot/normal/eclipse"; \
        mkdir -p "/opt/java/jdk-${major}"; \
        tar -xzf /tmp/jdk.tar.gz -C "/opt/java/jdk-${major}" --strip-components=1; \
        rm /tmp/jdk.tar.gz; \
    done

# -- Maven ------------------------------------------------------------------ #
# Fetched from archive.apache.org rather than dlcdn.apache.org: the mirror
# network drops older releases, the archive keeps them, so this build stays
# reproducible instead of breaking the day 3.9.9 is retired.
ARG MAVEN_VERSION=3.9.9
RUN set -eux; \
    curl -fsSL -o /tmp/maven.tar.gz \
        "https://archive.apache.org/dist/maven/maven-3/${MAVEN_VERSION}/binaries/apache-maven-${MAVEN_VERSION}-bin.tar.gz"; \
    mkdir -p /opt/maven; \
    tar -xzf /tmp/maven.tar.gz -C /opt/maven --strip-components=1; \
    rm /tmp/maven.tar.gz

# -- Gradle ----------------------------------------------------------------- #
ARG GRADLE_VERSION=8.10.2
RUN set -eux; \
    curl -fsSL -o /tmp/gradle.zip \
        "https://services.gradle.org/distributions/gradle-${GRADLE_VERSION}-bin.zip"; \
    unzip -q /tmp/gradle.zip -d /opt; \
    mv "/opt/gradle-${GRADLE_VERSION}" /opt/gradle; \
    rm /tmp/gradle.zip

# resolve_executable() (app/shared/command_runner.py) is shutil.which, so PATH
# is the only thing that makes mvn/gradle findable at runtime.
ENV JAVA_HOME=/opt/java/jdk-17 \
    GRADLE_HOME=/opt/gradle \
    PATH="/opt/java/jdk-17/bin:/opt/maven/bin:/opt/gradle/bin:${PATH}"

# -- Python dependencies ---------------------------------------------------- #
# Copied before the app so this layer is cached across code-only deploys.
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# -- Application ------------------------------------------------------------ #
COPY app ./app

# Writable job workspace. On Render's free tier this is EPHEMERAL -- it is wiped
# on every deploy and every idle spin-down. Mount a Persistent Disk here on a
# paid instance to keep reports, the Gradle cache and the vector store.
# Paths mirror app/core/config.py (storage_dir, support_tickets_dir,
# gradle_shared_cache_dir).
RUN mkdir -p /app/storage/migration-jobs \
             /app/storage/support-tickets \
             /app/storage/vector-store \
             /app/storage/.gradle-cache
ENV GRADLE_USER_HOME=/app/storage/.gradle-cache \
    PYTHONUNBUFFERED=1

# Render injects $PORT and expects the process to bind it on 0.0.0.0.
# Shell form is deliberate so $PORT expands at runtime.
#
# --workers 1 is required, not a preference: migrations run as in-process
# threads (app/application/pipelines/migration_execution_pipeline.py) and job
# state lives on local disk, so a second worker would poll jobs it cannot see.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1
