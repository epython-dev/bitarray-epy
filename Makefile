PYTHON=python


test:
	$(PYTHON) -c "import epython, bitarray; bitarray.test()"


clean:
	rm -rf bitarray/__pycache__ *.egg-info
