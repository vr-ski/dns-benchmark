#!/usr/bin/env python3
import sys, os, re, time
from argparse import ArgumentParser
from tempfile import NamedTemporaryFile
from zipfile import ZipFile
from multiprocessing import Pool


encoding = "utf-8"


def parse_alexa_top_csv(f, n):
	for line in f:
		line = line.decode(encoding)
		domain = line[line.index(",") + 1:].strip() # Extract the 2nd column of the csv only.
		yield domain
		if n > 0:
			n -= 1
			if not n:
				break


re_dig_answer_count = re.compile(", ANSWER: (\d+),")
re_query_time = re.compile(";; Query time: (\d+) msec")

def parse_dig_output(f):
	for line in f:
		m = re_dig_answer_count.search(line)
		if m:
			answer_count = int(m.group(1))
			continue
		m = re_query_time.match(line)
		if m:
			msec = int(m.group(1))
			yield answer_count, msec


def write_all(f, data):
	data = data.encode(encoding)
	while True:
		written = f.write(data)
		if written == len(data):
			break
		data = data[written:]


dig = "/usr/bin/dig"

def benchmark_dns(args):
	dns, domains_file = args

	dig_cmd = dig
	if dns != "system":
		dig_cmd += " @" + dns
	dig_cmd += " -f " + domains_file

	errors = 0
	dig_msec = 0
	count = 0

	t0 = time.clock_gettime(time.CLOCK_MONOTONIC_RAW)
	dig_proc = os.popen(dig_cmd)
	for answer_count, msec in parse_dig_output(dig_proc):
		errors += not answer_count
		dig_msec += msec
		count += 1
	t1 = time.clock_gettime(time.CLOCK_MONOTONIC_RAW)
	dig_rc = dig_proc.close()
	if dig_rc:
		print("{}: dig terminated with {}.".format(dns, dig_rc), file=sys.stderr)

	return count, errors, dig_msec, t1 - t0


def main():
	parser = ArgumentParser(description="Benchmark DNS query time.")
	parser.add_argument("-n", "--count", type=int, default=1000,
						help="The number of requests to make, 0 means no limit. Default is %(default)s.")
	parser.add_argument("-s", "--dns", default="system", metavar="IP",
						help="A comma-separated list of DNS server IP addresses. Default is %(default)s.")
	args = parser.parse_args()

	# Download Alexa top websites csv.
	alexa_top_csv = "top-1m.csv.zip"
	if not os.access(alexa_top_csv, os.R_OK):
		os.system("wget -O {0} http://s3.amazonaws.com/alexa-static/{0}".format(alexa_top_csv))

	if args.count >= 100:
		print("It may take minutes, please wait...")

	# To invoke dig only once per dns make a temporary file with all the domain names for dig to query.
	with NamedTemporaryFile(buffering=(1024 * 1024)) as domains_file:
		for domain in parse_alexa_top_csv(ZipFile(alexa_top_csv).open(alexa_top_csv.rstrip(".zip")), args.count):
			write_all(domains_file, domain + '\n')
		domains_file.flush()

		# Run benchmarks for different dns in parallel.
		dnss = [s.strip() for s in args.dns.split(',')]
		results = Pool(len(dnss)).map(benchmark_dns, zip(dnss, [domains_file.name] * len(dnss)))

	print("            dns,    time,    queries,     errors")
	for dns, (count, errors, dig_msec, total_sec) in zip(dnss, results):
		print("{:>15s}, {:7.3f}, {:10}, {:10}".format(dns, dig_msec * 1e-3, count, errors))


if __name__ == "__main__":
	main()

# Local Variables:
# mode: python
# python-indent-offset: 4
# tab-width: 4
# indent-tabs-mode: t
# coding: utf-8
# End:
