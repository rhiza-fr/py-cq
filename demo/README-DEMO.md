
## Create an asciinemo recording 
bash demo/run.sh

## View the result
docker run --rm -it -v "$(pwd)/demo/output:/output" cq-demo asciinema play /output/demo.cast