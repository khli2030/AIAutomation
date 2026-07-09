# Internal Ansible control-node SSH material (NEVER commit private keys).
#
# On the Ansible control server:
#   mkdir -p data/ansible-ssh
#   cp /path/to/ansible_control_key data/ansible-ssh/id_rsa
#   chmod 600 data/ansible-ssh/id_rsa
#   cp ~/.ssh/known_hosts data/ansible-ssh/known_hosts   # optional
#
# docker-compose mounts this directory read-only into celery-worker.
