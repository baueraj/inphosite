#!/usr/bin/env python
# -*- coding: utf-8 -*-

if __name__ == "__main__":
    from inpho.model import *
    from mako.template import Template
    
    node_q = Session.query(Node)
    idea_q = Session.query(Idea)
    thinker_q = Session.query(Thinker)
    profession_q = Session.query(Profession)
    nationality_q = Session.query(Nationality)
    
    nodes = node_q.all()
    ideas = idea_q.all()
    thinkers = thinker_q.all()
    professions = profession_q.all()
    nationalities = nationality_q.all()
    
    owl = Template(filename='/var/inpho/inphosite/scripts/owl/owl.xml',
                   default_filters=['decode.utf8', 'u', 'x'])
    print owl.render_unicode(nodes=nodes, thinkers=thinkers, ideas=ideas, 
               professions=professions, nationalities=nationalities).encode('utf-8',
               'replace')

else:
    raise Exception("Must be called from command line")


