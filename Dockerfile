# syntax=docker/dockerfile:1.6

# ---- Build stage ----
FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
ARG TARGETARCH
WORKDIR /src

COPY nuget.config ./
COPY src/GymAssistant.McpServer/GymAssistant.McpServer.csproj ./src/GymAssistant.McpServer/
COPY src/GymAssistant.McpServer/packages.lock.json ./src/GymAssistant.McpServer/

# GH Packages credentials passed as Docker build secrets from CI.
# Source `gym` is declared in nuget.config without credentials — authorize at runtime:
RUN --mount=type=secret,id=ghpat \
    --mount=type=secret,id=ghuser \
    NuGetPackageSourceCredentials_gym="Username=$(cat /run/secrets/ghuser);Password=$(cat /run/secrets/ghpat);ValidAuthenticationTypes=Basic" \
    dotnet restore ./src/GymAssistant.McpServer/GymAssistant.McpServer.csproj \
         -a $TARGETARCH --locked-mode

COPY src/ ./src/

RUN dotnet publish ./src/GymAssistant.McpServer/GymAssistant.McpServer.csproj \
    -c Release -o /app \
    -a $TARGETARCH \
    --no-restore \
    --self-contained true \
    /p:PublishTrimmed=true \
    /p:DebugType=none \
    /p:DebugSymbols=false

# ---- Runtime stage ----
FROM mcr.microsoft.com/dotnet/runtime-deps:10.0
WORKDIR /app
COPY --from=build /app/. .

# Non-root
USER $APP_UID

ENTRYPOINT ["./GymAssistant.McpServer"]
