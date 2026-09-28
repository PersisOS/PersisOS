#!/bin/bash
set -eu

echo 'Refreshing the system certificate trust store'
update-ca-certificates --fresh
