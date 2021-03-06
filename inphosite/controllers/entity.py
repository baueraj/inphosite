import logging
from time import sleep

from pylons import request, response, session, tmpl_context as c
from pylons.controllers.util import abort, redirect
from pylons import url
import re
import os.path
import csv

from inphosite.lib.base import BaseController, render
from inphosite.lib.rest import restrict, dispatch_on

from inpho import config
import inpho.model as model
from inpho.model import Session
from inpho.model import Entity, Node, Idea, Journal, Work, SchoolOfThought, Thinker
from inpho.model import Date
import inpho.corpus.sep as sep
import inphosite.lib.helpers as h
from sqlalchemy import or_
from sqlalchemy.sql.expression import func

from inphosite.lib.multi_get import multi_get
from urllib import quote_plus
import urllib
from urllib import urlopen
import simplejson

from xml.etree.ElementTree import parse
from xml.etree import ElementTree as ET
from sqlalchemy.exc import IntegrityError

from bs4 import BeautifulSoup

from rdflib.graph import ConjunctiveGraph
from SPARQLWrapper import SPARQLWrapper, JSON
from rdflib import URIRef
import csv

import sys
reload(sys)
sys.setdefaultencoding("utf-8")

log = logging.getLogger(__name__)

class DateException(Exception):
    pass

class EntityController(BaseController):
    _type = Entity
    _controller = 'entity'

    def data_integrity(self, filetype="html", redirect=False):
        if not h.auth.is_logged_in():
            abort(401)
        if not h.auth.is_admin():
            abort(403)

        entity_q = Session.query(Entity)
        c.entities = list(entity_q)

        c.missing_sep_dir = []
        c.mult_sep_dir = []

        for entity in c.entities:
            if not getattr(entity, 'sep_dir'):
                c.missing_sep_dir.append(entity)
            else:
                for comp_entity in c.entities:
                    if getattr(entity, 'sep_dir') == getattr(comp_entity, 'sep_dir') and entity != comp_entity:
                       c.mult_sep_dir.append(getattr(entity, 'sep_dir'))

        return render('entity/data_integrity.' + filetype)

    #separate from data_integrity for time required to check
    def load_check(self, filetype="html", redirect=False):
        if not h.auth.is_logged_in():
            abort(401)
        if not h.auth.is_admin():
            abort(403)

        entity_q = Session.query(Entity)
        c.entities = list(entity_q)

        c.load_error = []

        for entity in c.entities:
            try:
                urlopen(h.url('https://www.inphoproject.org', getattr(entity, 'url')))
            except Exception as e:
                c.load_error.append(entity)

        return render('entity/load_check.' + filetype)

    # UPDATE
    def update(self, id, terms=None):
        if not h.auth.is_logged_in():
            response.status_int = 401
            return "Unauthorized"
        if not h.auth.is_admin():
            response.status_int = 403
            return "Forbidden"

        #if no whitelist is passed in, go with default
        if terms is None:
            terms = ['sep_dir', 'searchstring', 'label']

        entity = h.fetch_obj(self._type, id)
        h.update_obj(entity, terms, request.params)

        # Check for redirect
        if request.params.get('redirect', False):
            h.redirect(
                h.url(controller=self._controller, action='view', id=entity.ID))
        else:
            # Issue an HTTP success
            response.status_int = 200
            return "OK"
    
    def missing_entity_search(self, query):
        query = quote_plus(query)
        url = 'http://plato.stanford.edu/cgi-bin/search/xmlSearcher.py?query=' + \
            query
        
        results = multi_get([url])[0][1]
        json = None
        values_dict = []
        if results:
            tree = ET.ElementTree(ET.fromstring(results))
            root = tree.getroot()
            json = []
            for element in root.getiterator('{http://a9.com/-/spec/opensearch/1.1/}Item'):
                dict = {}
                for iter in element.getiterator('{http://a9.com/-/spec/opensearch/1.1/}Location'):
                    dict['Location'] = iter.text
                json.append(dict)

            for j in range(len(json)):
                for key,value in json[j].iteritems():
                    values_dict.append(value)
            
        
        entities = Session.query(Entity).filter(Entity.sep_dir.in_(values_dict)).all()
        entities.sort(key = lambda entity: values_dict.index(entity.sep_dir))
        #raise Exception
        return entities

    def list(self, filetype='html'):
        entity_q = Session.query(self._type)
        #TODO: Remove the following line when Nodes are eliminated
        entity_q = entity_q.filter(Entity.typeID != 2)
        
        c.missing_entity = 0
        # get the list of entities
        #c.entities = entity_q.all()

        c.nodes = Session.query(Node).filter(Node.parent_id == None)
        c.nodes = c.nodes.order_by("name").all()

        c.query = request.params.get('q', '')
        c.query = c.query.strip()

        c.sep = request.params.get('sep', '')
        
        c.wiki = request.params.get('wiki', '')
        
        if request.params.get('sep_filter', False):
            entity_q = entity_q.filter(Entity.sep_dir != '')
        
        if c.sep:
            entity_q = entity_q.filter(Entity.sep_dir == c.sep) 
        
        if c.wiki:
            entity_q = entity_q.filter(Entity.wiki == c.wiki) 

        if c.query:
            o = or_(Entity.label.like(c.query+'%'), 
                    Entity.label.like('% '+c.query+'%'),
                    Entity.label.like('%-'+c.query+'%'))
            entity_q = entity_q.filter(o).order_by(func.length(Entity.label))

        c.total = entity_q.count()
        # limit must be the last thing applied to the query
        entity_q = entity_q.limit(request.params.get('limit', None))
        c.entities = entity_q.all()

        if filetype=='json':
            response.content_type = 'application/json'
       
        if request.params.get('redirect', False) and len(c.entities) == 1: 
            h.redirect(h.url(controller=self._controller, action='view', 
                             filetype=filetype, id=c.entities[0].ID), 
                       code=302)
        else:
	    #if there are no results, show the related SEP results
            if not c.entities:
                c.entities = self.missing_entity_search(c.query)
                if c.entities:
                    c.missing_entity = 1  
        #raise Exception
        #render the page
        return render('{type}/{type}-list.'.format(type=self._controller) 
                      + filetype)


    def related_entries(self, id, filetype='html'):
        c.entity = h.fetch_obj(Entity,id)
        
        related = sep.get_related()
        related = related[c.entity.sep_dir]
       
        c.entities = [] 
        for sep_dir in related:
            entity = Session.query(Entity).filter(Entity.sep_dir==sep_dir).first()
            if entity is not None:
                c.entities.append(entity)


        return render('entity/entity-list.%s' %(filetype))

    def list_new(self):
        if not h.auth.is_logged_in():
            response.status_int = 401
            return "Unauthorized"
        if not h.auth.is_admin():
            response.status_int = 403
            return "Forbidden"

        addlist = sep.new_entries()
        titles = sep.get_titles()
        
        c.entries = []
        
        #perform a fuzzy match for each page and construct an appropriate link
        for sep_dir in addlist:
            #create a link for each entry in addlist()
            link = h.url(controller='entity', action='new', 
                               label=titles[sep_dir], sep_dir=sep_dir)
            c.entries.append({ 'sep_dir' : sep_dir, 
                               'title' : titles[sep_dir], 
                               'link' : link,
                               'published' : sep.published(sep_dir)})

        return render('admin/newentries.html')

    def new(self):
        """ Form for creating a new entry """
        if not h.auth.is_logged_in():
            response.status_int = 401
            return "Unauthorized"
        if not h.auth.is_admin():
            response.status_int = 403
            return "Forbidden"

        # initialize template variables
        c.message = ""
        c.label = request.params.get('label', None)
        c.sep_dir = request.params.get('sep_dir', None)

        c.linklist = []
       
        if c.sep_dir and not c.label:
            try:
                c.label = sep.get_title(c.sep_dir)
            except KeyError:
                c.message = "Invalid sep_dir: " + c.sep_dir
                c.sep_dir = ""

        if c.sep_dir:
            fuzzypath = config.get('corpus', 'fuzzy_path')
            fuzzypath = os.path.join(fuzzypath, c.sep_dir)
            if os.path.exists(fuzzypath):
                with open(fuzzypath) as f:
                    matches = csv.reader(f)
                    for row in matches:
                        c.linklist.append(row)
            else:
                c.message = "Fuzzy match for " + c.sep_dir + " not yet complete."

            c.linklist.sort(key=lambda x: x[2], reverse=True)

        return render('entity/new.html')

    def create(self, entity_type=None, filetype='html', valid_params=None): 
        # check if user is logged in
        if not h.auth.is_logged_in():
            abort(401)
        if not h.auth.is_admin():
            abort(403)
        
        sep_dir = None 
        params = request.params.mixed()
        if entity_type is None:
            entity_type = int(params['entity_type'])
            del params['entity_type']

        if valid_params is None:
            if entity_type == 1: # Idea
                valid_params = ["sep_dir", "searchstring", "searchpattern",
                                "wiki"]
            elif entity_type == 3 or entity_type == 5: # Thinker or Work
                valid_params = ["sep_dir", "wiki"]
            elif entity_type == 4: # Journal
                valid_params = ["ISSN", "noesisInclude", "URL", "source",
                "abbr", "language", "student", "active", "wiki"]
            elif entity_type == 6: #School of Thought
                valid_params = ["sep_dir", "wiki"]
                
                
        if '_method' in params:
            del params['_method']
        if 'redirect' in params:
            del params['redirect']
        
        if 'sep_dir' in params:
            sep_dir = params['sep_dir']
            del params['sep_dir']
        if 'label' in params:
            label = params['label']
            del params['label']
        elif 'name' in params:
            label = params['name']
            del params['name']
        else:
            abort(400)
        for k in params.keys():
            if k not in valid_params:
                abort(400)

        # If entity exists, redirect and return HTTP 302
        c.entity = Session.query(Entity).filter(Entity.label==label).first()
        if c.entity:
            redirect(c.entity.url(filetype, action="view"), code=302)
        else:
            # Entity doesn't exist, create a new one.
            if entity_type == 1:
                c.entity = Idea(label, sep_dir=sep_dir)
            elif entity_type == 3:
                c.entity = Thinker(label, sep_dir=sep_dir)
            elif entity_type == 4:
                c.entity = Journal(label, sep_dir=sep_dir)
            elif entity_type == 5:
                c.entity = Work(label, sep_dir=sep_dir)
            elif entity_type == 6:
                c.entity = SchoolOfThought(label, sep_dir=sep_dir)
            else:
                raise NotImplementedError

            Session.add(c.entity)
            Session.commit()
            if redirect: 
                sleep(5) # TODO: figure out database slowness so this can be removed
                redirect(c.entity.url(filetype, action="view"), code=303)
            else:
                return "200 OK"
           

    def search(self, id, id2=None):
        # Grab ID(s) from database and get their search string(s).
        c.entity = h.fetch_obj(Entity, id)
        if id2 is None:
            c.entity2 = None
        else:
            c.entity2 = h.fetch_obj(Entity, id2)
        
        #creating link ID(s) for Bing + Google manual search by removing parentheses

        if c.entity2 is None:
            c.entity2_url_label = '' 
        else:
            c.entity2_url_label = ((c.entity2.label).split('('))[0]
            

        c.entity_url_label  = ((c.entity.label).split('('))[0]       

        # Run searches
        try:
            c.sep = EntityController._search_sep(c.entity, c.entity2)
        except Exception as e:
            c.sep = None

        try:
            c.noesis = EntityController._search_noesis(c.entity, c.entity2)
        except:
            c.noesis = None
        # c.bing = EntityController._search_bing(c.entity, c.entity2)
        return render('entity/search.html')

    def panel(self, id, id2): 
        c.entity = h.fetch_obj(Entity, id)
        c.entity2 = h.fetch_obj(Entity, id2)

        # redirection for Idea-Idea panels
        if isinstance(c.entity, Node):
            c.entity = c.entity.idea
            id = c.entity.ID
        if isinstance(c.entity2, Node):
            c.entity2 = c.entity2.idea
            id = c.entity2.ID
        if isinstance(c.entity, Idea) and isinstance(c.entity2, Idea):
            h.redirect(c.entity.url(action='panel', id2=id2), code=303)
        
        return self.search(id, id2)

    @staticmethod
    def _search_sep(entity, entity2):
        # Build search string
        if entity2 is None:
            searchstr = c.entity.web_search_string()
            c.sep_searchstr = quote_plus(searchstr.encode('utf8'))
        else:
            searchstr = entity.web_search_string() + " + " + \
                        entity2.web_search_string()
            c.sep_searchstr = quote_plus(searchstr.encode('utf8'))

        # Put together URL string
        url = "http://plato.stanford.edu/search/searcher.py?query=" + \
              c.sep_searchstr

        results = multi_get([url])[0][1]
        json = None
        if results:
            soup = BeautifulSoup(results, 'html.parser')
            divs = soup.findAll('div', {'class': 'result_listing'})
            json = []
            for div in divs:
                dict = {}
                dict['Text'] = div.find('a', {'class': 'l'}).contents
                dict['LongDescription'] = div.find('div', {'class': 'result_snippet'}).contents
                del dict['LongDescription'][-2:-1]
                dict['URL'] = div.find('a', {'class', 'l'})['href']
                dict['Location'] = 'test'
                json.append(dict)

        return json

    @staticmethod
    def _search_noesis(entity, entity2):
        # Concatenate search strings for each entity
        if entity2 is None:
            searchstr = c.entity.web_search_string()
            c.noesis_searchstr = quote_plus(searchstr.encode('utf8'))
        else:
            searchstr = entity.web_search_string() + " " + \
                        entity2.web_search_string()
            c.noesis_searchstr = quote_plus(searchstr.encode('utf8'))

        # Put together URL string
        api_key = "AIzaSyAd7fxJRf5Yj1ehBQAco72qqBSK1l0_p7c"
        c.noesis_cx = "001558599338650237094:d3zzyouyz0s"
        url = "https://www.googleapis.com/customsearch/v1?" + \
              "key=" + api_key + "&cx=" + c.noesis_cx + \
              "&q=" + c.noesis_searchstr

        # Get results and parse into json
        results = multi_get([url])[0][1]
        json = simplejson.loads(results) if results else None
        return json

    @staticmethod
    def _search_bing(entity, entity2):
        # Concatenate search strings for each entity
        if entity2 is None:
            searchstr = c.entity.web_search_string()
            c.bing_searchstr = quote_plus(searchstr.encode('utf8'))
        else:
            searchstr = entity.web_search_string() + " " + \
                        entity2.web_search_string()
            c.bing_searchstr = quote_plus(searchstr.encode('utf8'))

        # Put together URL string
        api_key = "34B53247AE710D6C3F5AFB35100F396E780C2CC4"
        url = "http://api.search.live.net/json.aspx" + \
              "?Appid=" + api_key  + "&query=" + \
              c.bing_searchstr + "&sources=web"

        # Get results and parse into json
        results = multi_get([url])[0][1]
        json = simplejson.loads(results) if results else None
        return json

    def view(self, id=None, filetype='html', format=None):
        c.sep_filter = request.params.get('sep_filter', False) 

        # Get entity and render template
        c.entity = h.fetch_obj(self._type, id, new_id=True)
       
        if filetype=='rdf':
            response.content_type = 'text/xml'
            return c.entity.graph().serialize(format=format)
      
        # Set MIME type of json files
        if filetype=='json':
            response.content_type = 'application/json'
            return c.entity.json()

        if self._type == Entity:
            h.redirect(c.entity.url(filetype), code=303)
        else:
            return render('{type}/{type}.'.format(type=self._controller) + 
                          filetype)


    def graph(self, id=None, id2=None, filetype='json'):
        c.entity = h.fetch_obj(Entity, id, new_id=True)
        if not id2:
            redirect(c.entity.url(filetype, action="graph"), code=303)
        else:
            c.entity2 = h.fetch_obj(Entity, new_id=True)
            redirect(c.entity.url(filetype, action="graph"), code=303)

    def _delete_searchpatterns(self, id):
        c.entity = h.fetch_obj(Entity, id, new_id=True)

        # add a new search pattern
        pattern = request.params.get('pattern', None)
        if pattern is None:
            abort(400)

        pattern = pattern.strip()

        # Boneheaded working around bogus associationproxy in SQLAlchemy 0.6.8
        # Why this isn't just c.entity.searchpatterns.remove(pattern)? who knows
        for spattern in c.entity._spatterns:
            if spattern.searchpattern == pattern:
                Session.delete(spattern)

        Session.commit()

        return "OK"

    @dispatch_on(DELETE='_delete_searchpatterns')
    def searchpatterns(self, id):
        c.entity = h.fetch_obj(Entity, id, new_id=True)

        # add a new search pattern
        pattern = request.params.get('pattern', None)
        if pattern is None:
            abort(400)
        
        if pattern not in c.entity.searchpatterns:
            c.entity.searchpatterns.append(unicode(pattern))

            Session.commit()

        return "OK"

    def _delete_date(self, id, id2):
        c.entity = h.fetch_obj(Entity, id, new_id=True)
        # get the date object
        date = self._get_date(id, id2)

        if date in c.entity.dates:
            idx = c.entity.dates.index(date)
            Session.delete(c.entity.dates[idx])
            Session.commit()
        
        return "OK"

    def _get_date(self, id, id2):
        """
        Helper function to create a date object, used in both deletion and
        creation.
        """
        c.entity = h.fetch_obj(Entity, id, new_id=True)
        id2 = int(id2)

        string = request.params.get('string', None)
        if string is not None:
            return Date.convert_from_iso(c.entity.ID, id2, string)

        # process form fields
        month = request.params.get('month', 0)
        try:
            month = None if month == '' else int(month)
        except:
            abort(400, "Invalid month.")
        
        day = request.params.get('day', 0)
        try:
            day = None if day == '' else int(day)
        except:
            abort(400, "Invalid day.")

        year = request.params.get('year', 0)
        try:
            year = None if year == '' else int(year)
        except:
            abort(400, "Invalid year.")

        era = request.params.get('era', None)

        # process range fields
        range = request.params.get('is_date_range', False)
        if range: 
            month_end = request.params.get('month_end', 0)
            try:
                month_end = None if month_end == '' else int(month_end)
            except:
                abort(400, "Invalid month_end.")
            
            day_end = request.params.get('day_end', 0)
            try:
                day_end = None if day_end == '' else int(day_end)
            except:
                abort(400, "Invalid day_end.")
    
            year_end = request.params.get('year_end', 0)
            try:
                year_end = None if year_end == '' else int(year_end)
            except:
                abort(400, "Invalid year_end.")

            era_end = request.params.get('era_end', None)

        # process era markers:
        if year and era == 'bce':
            year *= -1
        if range and year_end and era_end == 'bce':
            year_end *= -1

        # data integrity checks, raise a bad request if failed.
        # TODO: Make data integrity checks
        if not year:
            raise DateException("You must specify a year.")
        if year and not month and day:
            raise DateException("You must specify a month.")

        if range and (year > year_end):
            raise DateException("Start year must be before end year.")
        
        if not range:
            date = Date(c.entity.ID, id2,
                        year, month, day)
            date.entity = c.entity 
        else:
            date = Date(c.entity.ID, id2, 
                        year, month, day, 
                        year_end, month_end, day_end)
            date.entity = c.entity
        return date      

    def query_lode(self,id):
        var = "http://inpho.cogs.indiana.edu/thinker/"+id
        # initialize dictionaries to store temporray results
        dbPropResults = {}
        inpho_DB = {}
        DB_inpho = {}
	dbpedia_web = {}
        triples={}

        # init graphs for LODE and mapped data
        gLODE = ConjunctiveGraph()
        gReturn = ConjunctiveGraph()
        # import InPhO data
        gLODE.parse("http://inphodata.cogs.indiana.edu/lode/out_n3.20140207.rdf", format="n3")

        # builds a set of triples with the inpho id as the first entry and the
        # dbpedia id as the second 
        resultsLODE = gLODE.query("""
            SELECT ?thinker_LODE ?thinkerDB
            WHERE { ?thinker_LODE owl:sameAs ?thinkerDB 
                    FILTER (regex(str(?thinker_LODE),"http://inpho.cogs.indiana.edu","i")
                    && regex(str(?thinkerDB),"http://dbpedia.org/resource/","i")).
                   }
            """)
        
        # load in property mapping between inpho-dbpedia
        prop_map_filename = config.get_data_path('rdf_map.txt')
        with open(prop_map_filename,'r') as f:
            dbprops=csv.reader(f,delimiter='\t')
            for dbprop in dbprops:
                dbPropResults[dbprop[1]] = dbprop[0]
		dbpedia_web[dbprop[1].split(":")[1]]=dbprop[2]
		

        # iterate through triples and store mappings
        for triple in resultsLODE: 
            inpho_DB[str(triple[0])] = str(triple[1])#store the results in key as inpho url and value as dbpedia url
            DB_inpho[str(triple[1])] = str(triple[0])#store the results in key as dbpedia url and value as inpho url 
	   
	
	
        # queries for all relationships in dbpedia
        sparqlDB = SPARQLWrapper("http://inpho-dataserve.cogs.indiana.edu:8890/sparql/")
        sparqlDB.setReturnFormat(JSON)
        for inpho,DB in inpho_DB.iteritems():
            predicate = {}
            #for dbprop in dbPropResults:
            if(str(DB_inpho.get(DB))== var):
		for dbprop in dbPropResults:
                    sparqlDB.setQuery(""" PREFIX dbpprop: <http://dbpedia.org/ontology/>
                                      SELECT ?b  WHERE { <"""+DB+"""> """+dbprop+""" ?b.
                                                        FILTER (regex(str(?b),"dbpedia.org/resource/","i")).
                                                        }""")
                    resultsDB = sparqlDB.query().convert()
                    predicate[dbprop] = resultsDB["results"]["bindings"]
            	triples[DB] = predicate
        
        #retrieve native python object
        c.entity = h.fetch_obj(Entity, id, new_id=True)
	existing_predicate_list=[]
	existing_object_list=[]

        predicates_to_compare = ['influenced', 'influenced_by', 'teachers', 'students']


        for subject,predicate in triples.iteritems():
            for predicate1, objectn in predicate.iteritems():
                predicate_to_match=predicate1.split(":")[1]
	        attr=getattr(c.entity,dbpedia_web[predicate_to_match])
              
		for attr1 in attr:
               	        if(dbpedia_web[predicate_to_match] in predicates_to_compare) :
				existing_predicate_list.append(dbpedia_web[predicate_to_match] +':'+attr1.wiki)




        # maps from dbpedia relationships back to inpho relationships
        for subject,predicate in triples.iteritems():
            #attr = getattr(c.entity, predicate)
	    #raise Exception
		
	    for predicate1, objectn in predicate.iteritems():
		
	      
				
	
                for object1 in objectn:                       
		   #temp_str=dbpedia_web[predicate1.split(":")[1]] + ':'+str(object1['b']['value']).split("/")[len(str(object1['b']['value']).split("/"))-1].replace("_"," ")
		   temp_str=dbpedia_web[predicate1.split(":")[1]] + ':'+str(object1['b']['value']).split("/")[len(str(object1['b']['value']).split("/"))-1]

                   
	#	   raise Exception
	           if temp_str not in existing_predicate_list:     
		  # returns the inphoid for the object
                   	DB_Entry = DB_inpho.get(object1['b']['value'])#reverse lookup for the inpho data check	    

                    	# if there is not an inpho id, leave it as the dbpedia id
                   	if(DB_Entry == None):
                        	gReturn.add((URIRef(subject),URIRef(dbPropResults.get(predicate1)),URIRef(object1['b']['value'])))
                   	else:
                        	# return the properly mapped id
                        	# TODO: use attr to filter DB_Entry
                        	gReturn.add((URIRef(subject),URIRef(dbPropResults.get(predicate1)),URIRef(DB_Entry)))
                     
                      #  if "Francisco" in str(object1['b']['value']).split("/")[len(str(object1['b']['value']).split("/"))-1].replace("_", ):
		   
#        raise Exception                  
        return gReturn.serialize();

    @dispatch_on(DELETE='_delete_date')
    def date(self, id, id2, filetype='json'):
        """
        Creates a date object, associated to the id with the relation type of
        id2.
        """
        try:
            date = self._get_date(id, id2)
        except DateException as e:
            # TODO: Cleanup this workaround for the Pylons abort function not
            # passing along error messages properly to the error controller.
            response.status = 400
            return str(e)

        try:
            Session.add(date)
            Session.commit()
        except IntegrityError:
            # skip over data integrity errors, since if the date is already in
            # the db, things are proceeding as intended.
            pass

        return "OK"

    #DELETE
    @restrict('DELETE')
    def delete(self, id=None):
        if not h.auth.is_logged_in():
            abort(401)
        if not h.auth.is_admin():
            abort(403)

        idea = h.fetch_obj(Entity, id, new_id=True)
        
        h.delete_obj(idea)

        # Issue an HTTP success
        response.status_int = 200
        return "OK"
