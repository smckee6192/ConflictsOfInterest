from git import Repo
import urllib2
import json
import config_loader
import os

def pull_repositories():
	repoData = urllib2.urlopen('https://api.github.com/search/repositories?q=stars:>1&sort=stars&order=desc').read()
	jsonData = json.loads(repoData)
	repos = []

	banned = ['legacy-homebrew', 'meteor', 'gitignore', 'You-Dont-Know-JS', 'Font-Awesome', 'free-programming-books', 'html5-boilerplate', 'the-art-of-command-line']

	for each in jsonData['items']:
	    if each['name'] not in banned:
	        repos.append( (each['name'], each['html_url']) )

	for idx,r in enumerate(repos):
	    print("%d - url: %s, folder: %s%s" % (idx + 1, r[1], config_loader.get('DOWNLOAD_PATH'), r[0]))
	    url = r[1]
	    path = config_loader.get('DOWNLOAD_PATH') + r[0]
	    if os.path.isdir(path) and os.path.exists(path):
	    	continue
	    else:
	    	Repo.clone_from(url, path)