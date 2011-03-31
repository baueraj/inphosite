from php import PHP
from inphosite.model.meta import Session
from inphosite.model import Entity, SEPEntry, Fuzzymatch

def convertSS(choicestring, ioru):
    #takes one of the output choices from setup_SSL(), as well as whether we are dealing with intersection or union
    #returns a pair of string--[searchstring, searchpattern]
    #where relevant, assume union by default (e.g. if ioru = anything other than 'i', union is implemented)
    #get first three characters of string to see which option from setup_SSL() we have
    #eventually replace choicestring in output with output from Jaimie's function
    split = choicestring.split(': ')

    #get # choice in "option" and string to be massaged in "string"
    sstring = split[1]
    option = split[0]

    ideas = sstring.split(' <and> ')

    #Options #1, 2  --do nothing, return sstring
    
    #3,4,5,6, 11:  idea1<and>idea2 ...<and>idean
    if option == '3' or option == '4' or option == '5' or option=='6' or option == '11':
        if ioru == 'i':
            sstring = "<i>".join(ideas)
            #spattern = "(( " + ideas[0] + "(
        else:
            sstring = "<u>".join(ideas)
    
    #7:  <idea1> and <idea2> and <area>
    #change to: 
    #(Idea1<i>area)<u>(idea2<i>area) or
    #(idea1<i>area)<i>(idea2<i>area)
    #8 <adj idea1> and <adj idea2> and <area>)
    #to (adj idea1<i>area)<u>(adj idea2<i>area)
    #(adj idea1<i>area)<i>(adj idea2<i>area)
    elif option == '7' or option == '8':
        ideaarea1 = '(' + "<i>".join([ideas[0], ideas[2]]) + ')'
        ideaarea2 = '(' + "<i>".join([ideas[1], ideas[2]]) + ')'
        if ioru == 'i':
            sstring = "<i>".join([ideaarea1, ideaarea2]) 
        else:
            sstring = "<u>".join([ideaarea1, ideaarea2])
    
    #Option 9: <idea> and <area1> and <area2> 
    #(idea<i>area1)<u>(idea<i>area2)
    #(idea<i>area1)<i>(idea<i>area2)
    elif option == '9':
        ideaarea1 = '(' + "<i>".join([ideas[0], ideas[1]]) + ')'
        ideaarea2 = '(' + "<i>".join([ideas[0], ideas[2]]) + ')'
        if ioru == 'i':
            sstring = "<i>".join([ideaarea1, ideaarea2]) 
        else: 
            sstring = "<u>".join([ideaarea1, ideaarea2])

    #<idea1> and <idea2> and <adj area1> and <adj area2>)
    #to(idea1<i>(area1<u>area2))<u>(idea2<i>(area1<u>area2))
    #(idea1<i>idea2)<i>(area1<u>area2)
    elif option == '10':
        areas = '(' + "<u>".join([ideas[2], ideas[3]]) + ')'
        jointideas = '(' + "<i>".join([ideas[0], ideas[1]]) + ')'
        ideaarea1 = '(' + "<i>".join([ideas[0], areas]) + ')'
        ideaarea2 = '(' + "<i>".join([ideas[1], areas]) + ')'
        if ioru == 'i':
            sstring = "<i>".join([jointideas, areas])
        else:
            sstring = "<u>".join([ideaarea1, ideaarea2])
            
    elif option == '11' or option == '12' or option == '13' or option == '14':
        if ioru == 'i':
            sstring = "<i>".join(ideas)
        else:
            sstring = "<u>".join(ideas)
    
    elif option == '15':
        if ioru == 'i':
            sstring = "<i>".join(ideas)
        else: 
            phil = ideas[:1]
            ideas = ideas[1:]
            sstring = phil[0] + "<i>(" + "<u>".join(ideas) + ")"

    return [sstring, choicestring]

def fuzzymatch(string1):
    #note:  fuzzymatch.php must be in php path, e.g.  /usr/lib/php/!!!
    #put in a cron job that runs every half hour for new entries?
    
    entities = Session.query(Entity)
    
    
    matches = []
    
    ##string1 = string1.decode('utf8')
    
    for entity in entities:
        php = PHP("require 'fuzzymatch.php';")
        #php = PHP()
        #print "testing " + entity.label.encode('utf8') + " against " + string1.encode('utf8') + "\n"
        
        code = '$string1 = utf8_decode("' + string1.encode('utf8') + '");'
        
        #code = code + "$string2 = '" + entity.label.encode('latin-1', 'replace') + "';"
        #code = code + "print $string1; print $string2;"
        #print code + '$string2 = utf8_decode("' + entity.label.encode('utf8') + '");'
        code = code + '$string2 = utf8_decode("' + entity.label.encode('utf8') + '");'
        code = code + """print fuzzy_match($string1, $string2, 2);"""
        
        verdict = php.get_raw(code)
        #print "verdict is " + verdict + "\n"
    
        if float(verdict)>=.5:
            #print entity.label + " is a match!\n"
            entity.matchvalue = verdict
            matches.append(entity)
    
    return matches

def fuzzymatchall(SEPEntrieslist):
    #takes outputs from addlist() and saves all fuzzy match IDs to SEPEntry.fuzzymatch with verdicts (percent of words matched)
    #now change so that it only updates ones that don't currently have a fuzzymatchlist
    
    #clear out fuzzymatch table--otherwise old fuzzies will accumulate, and nobody wants that
    delquery = Session.query(Fuzzymatch)
    delquery.delete()
    Session.flush()
    Session.commit()
    
    
    for SEPEntry in SEPEntrieslist:
            print "working on " + SEPEntry.title + "\n"
            entities = Session.query(Entity)
            
            #exclude journals and nodes from fuzzy matching
            entities = entities.filter(Entity.typeID != 2)
            entities = entities.filter(Entity.typeID != 4)
            
            #reset fuzzymatches for that entry
            #SEPEntry.fuzzymatches = ""
    
            
            ##string1 = string1.decode('utf8')
            
            for entity in entities:
                php = PHP("set_include_path('/usr/lib/php/');")
                php = PHP("require 'fuzzymatch.php';")
                #php = PHP()
                #print "testing " + entity.label.encode('utf8') + " against " + string1.encode('utf8') + "\n"
                
                code = '$string1 = utf8_decode("' + SEPEntry.title.encode('utf8') + '");'
                
                #code = code + "$string2 = '" + entity.label.encode('latin-1', 'replace') + "';"
                #code = code + "print $string1; print $string2;"
                #print code + '$string2 = utf8_decode("' + entity.label.encode('utf8') + '");'
                code = code + '$string2 = utf8_decode("' + entity.label.encode('utf8') + '");'
                code = code + """print fuzzy_match($string1, $string2, 2);"""
                
                verdict = php.get_raw(code)
                #print "verdict is " + verdict + "\n"
                verdict = verdict.split(',')
            
                if float(verdict[0])>=.20:
                    #print entity.label + " is a match!\n"
                    #entity.matchvalue = verdict
                    #string = SEPEntry.fuzzymatches + "|" + str(entity.ID) + "," + verdict
                    
                    #if len(string) < 400:
                    #    SEPEntry.fuzzymatches = SEPEntry.fuzzymatches + "|" + str(entity.ID) + "," + verdict
                    #else:
                    #    print "sorry, too many matches!  Can't add " + str(entity.ID) + " to fuzzy matches; over 400 chars."
                    fmatch = Fuzzymatch(entity.ID)
                    fmatch.sep_dir = SEPEntry.sep_dir
                    fmatch.strength = verdict[0]
                    fmatch.edits = verdict[1]
                    
                    SEPEntry.fmatches.append(fmatch)
                    
                    
            Session.flush()
            Session.commit()


def fuzzymatchtest(string1, string2):
    #note:  fuzzymatch.php must be in php path, e.g.  /usr/lib/php/!!!
    php = PHP("require 'fuzzymatch.php';")
    #php = PHP()
    
    code = "$string1 = '" + string1 + "';"
    code = code + "$string2 = '" + string2.encode('latin-1', 'replace') + "';"
    #code = code + "print $string1; print $string2;"
    code = code + """print fuzzy_match($string1, $string2, 2);"""
    
    return php.get_raw(code)
