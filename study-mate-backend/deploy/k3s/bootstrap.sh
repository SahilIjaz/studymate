#!/usr/bin/env bash
# One-shot setup of a single-node k3s cluster for the StudyMate API on a fresh
# Ubuntu VM (tested target: Oracle Cloud Always Free ARM, Ubuntu 22.04/24.04).
#
# Usage, on the VM:
#   export GEMINI_API_KEY=...  DUCKDNS_TOKEN=...
#   curl -fsSL https://raw.githubusercontent.com/SahilIjaz/studymate/main/study-mate-backend/deploy/k3s/bootstrap.sh | bash
#
# Idempotent: safe to re-run after changing the manifests.
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/SahilIjaz/studymate.git}"
CERT_MANAGER_VERSION="${CERT_MANAGER_VERSION:-v1.17.2}"
: "${GEMINI_API_KEY:?set GEMINI_API_KEY}"
: "${DUCKDNS_TOKEN:?set DUCKDNS_TOKEN}"

log() { printf '\n\033[1;33m==> %s\033[0m\n' "$*"; }

log "Opening the firewall for HTTP/HTTPS (Oracle images ship with iptables rules that drop them)"
if command -v iptables >/dev/null; then
  sudo iptables -I INPUT -p tcp --dport 80  -j ACCEPT
  sudo iptables -I INPUT -p tcp --dport 443 -j ACCEPT
  sudo apt-get install -y -qq netfilter-persistent iptables-persistent >/dev/null 2>&1 || true
  sudo netfilter-persistent save >/dev/null 2>&1 || true
fi

log "Installing k3s (Traefik ingress included)"
if ! command -v k3s >/dev/null; then
  curl -sfL https://get.k3s.io | sh -
fi
mkdir -p "$HOME/.kube"
sudo cp /etc/rancher/k3s/k3s.yaml "$HOME/.kube/config"
sudo chown "$(id -u):$(id -g)" "$HOME/.kube/config"
export KUBECONFIG="$HOME/.kube/config"
kubectl wait --for=condition=Ready node --all --timeout=180s

log "Installing cert-manager $CERT_MANAGER_VERSION"
kubectl apply -f "https://github.com/cert-manager/cert-manager/releases/download/${CERT_MANAGER_VERSION}/cert-manager.yaml"
kubectl -n cert-manager rollout status deploy/cert-manager-webhook --timeout=180s

log "Fetching manifests"
if [ -d "$HOME/studymate/.git" ]; then
  git -C "$HOME/studymate" pull --ff-only
else
  git clone --depth 1 "$REPO_URL" "$HOME/studymate"
fi
cd "$HOME/studymate/study-mate-backend"

log "Creating secrets (idempotent)"
kubectl create namespace studymate --dry-run=client -o yaml | kubectl apply -f -
kubectl -n studymate create secret generic studymate-api-secrets \
  --from-literal=GEMINI_API_KEY="$GEMINI_API_KEY" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl -n studymate create secret generic duckdns \
  --from-literal=token="$DUCKDNS_TOKEN" \
  --dry-run=client -o yaml | kubectl apply -f -

log "Pointing DuckDNS at this VM"
curl -fsS "https://www.duckdns.org/update?domains=study-mate-ai&token=${DUCKDNS_TOKEN}&ip=" && echo

log "Deploying"
kubectl apply -k deploy/k8s/overlays/production
kubectl -n studymate rollout status deploy/studymate-api --timeout=300s

log "Waiting for the Let's Encrypt certificate"
kubectl -n studymate wait --for=condition=Ready certificate/studymate-api-tls --timeout=300s || \
  echo "Certificate not ready yet; check: kubectl -n studymate describe certificate studymate-api-tls"

log "Done"
echo "API:  https://study-mate-ai.duckdns.org/health"
echo "Logs: kubectl -n studymate logs deploy/studymate-api -f"
