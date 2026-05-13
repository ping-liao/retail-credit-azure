#!/bin/bash
RG="rg-retail-credit"
echo "WARNING: This deletes ALL resources in $RG"
read -p "Type 'yes' to confirm: " confirm
if [ "$confirm" == "yes" ]; then
  az group delete --name $RG --yes --no-wait
  echo "Deletion started. Check Azure Portal for progress."
else
  echo "Cancelled."
fi
