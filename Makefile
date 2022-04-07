PYTHON=python


test:
	$(PYTHON) -c "import bitarray; bitarray.test()"


clean:
	rm -rf bitarray/__pycache__ *.egg-info
