#!/usr/bin/env bash
set -euo pipefail
umask 077

if [[ ${GA_RUNNER_MODE:-} == local ]]; then
  [[ ${RUNNER_OS:-} == macOS && ${RUNNER_ARCH:-} == ARM64 ]] || {
    echo 'Local CI requires the registered macOS ARM64 runner.' >&2; exit 1;
  }
  [[ ${GA_REPOSITORY_PRIVATE:-} == true && ${GA_ACTOR:-} != 'dependabot[bot]' ]] || {
    echo 'Local CI accepts only trusted private-repository events.' >&2; exit 1;
  }
  if [[ ${GA_EVENT_NAME:-} == pull_request ]]; then
    [[ ${GA_HEAD_REPOSITORY:-} == "${GITHUB_REPOSITORY:?}" ]] || {
      echo 'Fork pull requests cannot use the workstation runner.' >&2; exit 1;
    }
  fi
fi

if [[ ${GA_PREPARE_DOCKER:-false} == true ]]; then
  # Resolve the existing Desktop context before using a clean client config.
  docker_host=${DOCKER_HOST:-$(docker context inspect --format '{{.Endpoints.docker.Host}}')}
  [[ "$docker_host" == unix://* && "$docker_host" != *$'\n'* && "$docker_host" != *$'\r'* ]] || {
    echo 'CI requires a local Unix-socket Docker daemon, not a remote daemon.' >&2; exit 1;
  }
  [[ $(docker version --format '{{.Server.Os}}') == linux ]] || {
    echo 'CI requires Linux containers.' >&2; exit 1;
  }
  task_docker_config=$(mktemp -d "${RUNNER_TEMP:?}/ga-docker.XXXXXX")
  chmod 700 "$task_docker_config"
  # Preserve only official Desktop plugin discovery. Never copy personal auths,
  # contexts or credential-store settings from ~/.docker/config.json.
  if [[ ${RUNNER_OS:-} == macOS && -d /Applications/Docker.app/Contents/Resources/cli-plugins ]]; then
    printf '%s\n' '{"cliPluginsExtraDirs":["/Applications/Docker.app/Contents/Resources/cli-plugins"]}' > "$task_docker_config/config.json"
  else
    printf '%s\n' '{}' > "$task_docker_config/config.json"
  fi
  {
    printf 'DOCKER_HOST=%s\n' "$docker_host"
    printf 'DOCKER_CONFIG=%s\n' "$task_docker_config"
  } >> "${GITHUB_ENV:?}"
fi
