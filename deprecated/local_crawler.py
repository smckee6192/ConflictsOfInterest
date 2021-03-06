from git import *
from git.compat import defenc
import inspect
import config_loader
import data_manager
import json, urllib2
import os, sys
from subprocess import Popen, PIPE
import pattern_classifier as classifier
import puller
from datetime import datetime
import time
import notifier

REPO_PATH = config_loader.get('REPO_PATH')
EMPTY_TREE_SHA = "4b825dc642cb6eb9a060e54bf8d69288fbee4904" # Git has a well-known, or at least sort-of-well-known, empty tree with this SHA1
DEBUG = False

def main():
    if DEBUG:
        repo = Repo(REPO_PATH)
        repo.git.checkout("master")
        project = project = repo.remotes[0].url.split(":")[-1][:-4].split("/")[-1]

        mergesDict, commitsDict = data_manager.loadDictionaries(repo)

        for i,commitHash in enumerate(mergesDict):
            commit = commitsDict[commitHash]
            print commit
            #print getDiff(commit)
            parent1SHA, parent2SHA = mergesDict[commitHash]
            conflicts = findConflicts(repo, list(commit.parents))
            for file in conflicts:
                if len(file) < 2:
                    print "WARNING: list index out of range"
                    continue
                print classifier.classifyResolutionPattern(file[0]['lines'], file[1]['lines'], getDiff(commit))
    else:
        try:
            puller.pull_repositories()
            download_dir = config_loader.get('DOWNLOAD_PATH')
            downloadedRepos = [x[0] for x in walklevel(download_dir)][1:]
            for downloadedRepoPath in downloadedRepos:
                print "downloadedRepoPath: %s" % downloadedRepoPath
                repo = Repo(downloadedRepoPath)
                repo.git.checkout("master")
                project = downloadedRepoPath.split('/')[-1]

                if not project == 'reveal.js':
                    continue

                log(project, ("repo: %s, lang: %s" % (repo.remotes[0].url, getLang(repo)))) 
                mergesDict, commitsDict = data_manager.loadDictionaries(repo)

                for i,commitHash in enumerate(mergesDict):
                    print "commit: %s" % commitHash
                    commit = commitsDict[commitHash]
                    conflicts = findConflicts(repo, list(commit.parents))
                    parent1SHA, parent2SHA = mergesDict[commitHash]

                    log(project, ("commit: %s, conflict count: %d" % (commit, len(conflicts))))

                    for file in conflicts:
                        if len(file) < 2:
                            print "WARNING: list index out of range, skipping"
                            continue
                        print "conflicting: %s" % file[0]['file']
                        line_count = len(file[0]['lines'].splitlines()) + len(file[1]['lines'].splitlines())
                        classification = classifier.classifyResolutionPattern(file[0]['lines'], file[1]['lines'], getDiff(commit))
                        log(project, "conflict file: %s, size: %d lines, pattern: %s" % (file[0]['file'], line_count, classification))
        except:
            print("Unexpected error:", sys.exc_info()[0])
            timestamp = datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S')
            notice = "Exception received by local_crawler.py on %s.\n\nException: %s" % (timestamp, sys.exc_info()[0])
            for recipient in config_loader.get('NOTIFY'):
                notifier.send_notice(config_loader.get('GMAIL_AUTH')['username'], config_loader.get('GMAIL_AUTH')['password'], "CS569_FinalProject failure detected", recipient, None, notice)
            raise

def log(project, str):
    ts = datetime.today().strftime('%Y-%m-%d')
    f = open('data/'+project+'.'+ts+'.log', 'a+')
    f.write(str + "\n")
    f.close()

def walklevel(some_dir, level=1):
    some_dir = some_dir.rstrip(os.path.sep)
    assert os.path.isdir(some_dir)
    num_sep = some_dir.count(os.path.sep)
    for root, dirs, files in os.walk(some_dir):
        yield root, dirs, files
        num_sep_this = root.count(os.path.sep)
        if num_sep + level <= num_sep_this:
            del dirs[:]

def getDiff(commit):
    msg = ""
    if not commit.parents:
        diff = commit.diff(EMPTY_TREE_SHA, create_patch=True)
    else:
        diff = commit.diff(commit.parents[0], create_patch=True)

    for k in diff:
        try:
            msg = k.diff.decode(defenc)
        except UnicodeDecodeError:
            continue
    additions = ''.join([x[1:] for x in msg.splitlines() if x.startswith('+')])
    return additions

# determine the programming language most used in a repository
def getLang(repo):
    remote_url = repo.remotes[0].url
    
    # handle SSH url, else handle HTTPS url; Warning: BLACK MAGIC!!!
    if (remote_url[-4:] == '.git'):
        owner = remote_url.split(":")[-1][:-4].split("/")[-2]
        project = remote_url.split(":")[-1][:-4].split("/")[-1]
    else:
        owner = remote_url.split("/")[-2]
        project = remote_url.split("/")[-1]

    rawData = urllib2.urlopen('https://api.github.com/repos/' + owner + '/' + project + '/languages').read()
    jsonData = json.loads(rawData)
    return max(jsonData, key=jsonData.get)

def getCommit(commitsDict, SHA):
    return commitsDict[SHA]

def findConflicts(repo, commits):
    conflictSet = []
    old_wd = os.getcwd()
    os.chdir(repo.working_dir)

    if len(commits) < 2:
        # not enough commits for a conflict to emerge
        return conflictSet
    else:
        try:
            firstCommitStr = commits.pop().hexsha

            p = Popen(["git", "checkout", firstCommitStr], stdin=None, stdout=PIPE, stderr=PIPE)
            out, err = p.communicate()
            rc = p.returncode

            arguments = ["git", "merge"] + map(lambda c:c.hexsha, commits)
            p = Popen(arguments, stdin=None, stdout=PIPE, stderr=PIPE)
            out, err = p.communicate()
            rc = p.returncode

            if "CONFLICT" in out:
                notification_lines = [x for x in out.splitlines() if "CONFLICT" in x]
                conflict_filenames = []
                for line in notification_lines:
                    if "Merge conflict in " in line:
                        conflict_filenames.append(line.split('Merge conflict in ')[-1])
                    if "deleted in " in line:
                        conflict_filenames.append(line.split(' deleted in ')[0].split(': ')[-1])
                    else:
                        continue

                for filename in conflict_filenames:
                    conflictSet.append(getConflictSet(repo, filename))

                p = Popen(["git", "merge", "--abort"], stdin=None, stdout=PIPE, stderr=PIPE)
                out, err = p.communicate()
                rc = p.returncode
                return conflictSet

        finally:
            try:
                # Completely reset the working state after performing the merge
                p = Popen(["git", "clean", "-xdf"], stdin=None, stdout=PIPE, stderr=PIPE)
                out, err = p.communicate()
                rc = p.returncode
                p = Popen(["git", "reset", "--hard"], stdin=None, stdout=PIPE, stderr=PIPE)
                out, err = p.communicate()
                rc = p.returncode
                p = Popen(["git", "checkout", "."], stdin=None, stdout=PIPE, stderr=PIPE)
                out, err = p.communicate()
                rc = p.returncode
            finally:
                # Set the working directory back
                os.chdir(old_wd)

    return conflictSet

def getConflictSet(repo, filename):
    path = repo.working_dir + '/' + filename    
    content = open(filename, 'r').read()
    
    if '=======' not in content:
        print "STRANGENESS!: no conflict for %s" % path
        return []
    if len(content.split('=======')) > 2:
        print "MORE WEIRDNESS!: more than one conflict for %s" % path
        return []
    else: 
        (left, right) = content.split('=======')
    leftSHA = left.splitlines()[0].split(' ')[-1]
    rightSHA = right.splitlines()[-1].split(' ')[-1]
    if leftSHA == 'HEAD':
        leftSHA = str(repo.head.commit)
    if rightSHA == 'HEAD':
        rightSHA = str(repo.head.commit)
    left = ''.join(left.splitlines(True)[1:])       # remove first line
    right = ''.join(right.splitlines(True)[:-1])    # remove last line

    leftDict = {}
    leftDict['file'] = path
    leftDict['SHA'] = leftSHA
    leftDict['lines'] = left
    rightDict = {}
    rightDict['file'] = path
    rightDict['SHA'] = rightSHA
    rightDict['lines'] = right

    return [leftDict, rightDict]

# returns name of current branch
def getCurrentBranch(repo):
    return repo.git.rev_parse('HEAD', abbrev_ref=True)
    # git rev-parse --abbrev-ref HEAD

if __name__ == "__main__":
    main()