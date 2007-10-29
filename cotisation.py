# -*- coding: utf-8 -*-

##    This file is part of Gertrude.
##
##    Gertrude is free software; you can redistribute it and/or modify
##    it under the terms of the GNU General Public License as published by
##    the Free Software Foundation; either version 2 of the License, or
##    (at your option) any later version.
##
##    Gertrude is distributed in the hope that it will be useful,
##    but WITHOUT ANY WARRANTY; without even the implied warranty of
##    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
##    GNU General Public License for more details.
##
##    You should have received a copy of the GNU General Public License
##    along with Gertrude; if not, write to the Free Software
##    Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

import datetime
from functions import *

class CotisationException(Exception):
    def __init__(self, errors):
        self.errors = errors

NO_ADDRESS = 1
NO_NOM = 2
NO_REVENUS = 4
REVENUS_ANNEE_PRECEDENTE = 8
RATTRAPAGE_SEPTEMBRE = 16

class Cotisation(object):
    def __init__(self, inscrit, periode, options=0):
        self.inscrit = inscrit
        self.debut, self.fin = periode
        self.options = options
        errors = []
        if not inscrit.prenom or (not options & NO_NOM and not inscrit.nom):
            errors.append(u" - L'état civil de l'enfant est incomplet.")
        if not options & NO_ADDRESS and (not inscrit.code_postal or not inscrit.ville):
            errors.append(u" - L'adresse de l'enfant est incomplète.")
        if not inscrit.papa.prenom or not inscrit.maman.prenom or not inscrit.papa.nom or not inscrit.maman.nom:
            errors.append(u" - L'état civil des parents est incomplet.")
        if self.debut is None:
            errors.append(u" - La date de début de la période n'est pas renseignée.")
            raise CotisationException(errors)
        revenus_debut = self.debut
        if options & REVENUS_ANNEE_PRECEDENTE:
            revenus_debut = datetime.date(self.debut.year-1, self.debut.month, self.debut.day)
        self.revenus_papa = Select(inscrit.papa.revenus, revenus_debut)
        if not options & NO_REVENUS and (self.revenus_papa is None or self.revenus_papa.revenu == ''):
            errors.append(u" - Les déclarations de revenus du papa sont incomplètes.")
        self.revenus_maman = Select(inscrit.maman.revenus, revenus_debut)
        if not options & NO_REVENUS and (self.revenus_maman is None or self.revenus_maman.revenu == ''):
            errors.append(u" - Les déclarations de revenus de la maman sont incomplètes.")
        self.bureau = Select(creche.bureaux, self.debut)
        if self.bureau is None:
            errors.append(u" - Il n'y a pas de bureau à cette date.")
        self.bareme_caf = Select(creche.baremes_caf, revenus_debut)
        if self.bareme_caf is None:
            errors.append(u" - Il n'y a pas de barème CAF à cette date.")
        self.inscription = inscrit.getInscription(self.debut)
        if self.inscription is None:
            errors.append(u" - Il n'y a pas d'inscription à cette date.")
            raise CotisationException(errors)

        self.mode_garde = self.inscription.mode
        jours_garde = 0
        for jour in range(5):
            for tranche in range(3):
                if self.inscription.periode_reference[jour][tranche]:
                    jours_garde += 1
                    break
        if self.inscription.mode == 0 and jours_garde < 3:
            errors.append(u" - La semaine type de l'enfant est incomplète pour le mode d'accueil choisi.")

        if len(errors) > 0:
            raise CotisationException(errors)

        self.assiette_annuelle = float(self.revenus_papa.revenu) 
        if self.revenus_papa.chomage:
            self.abattement_chomage_papa = 0.3 * float(self.revenus_papa.revenu)
            self.assiette_annuelle -= self.abattement_chomage_papa

        self.assiette_annuelle += float(self.revenus_maman.revenu)
        if self.revenus_maman.chomage:
            self.abattement_chomage_maman = 0.3 * float(self.revenus_maman.revenu)
            self.assiette_annuelle -= self.abattement_chomage_maman

        if self.assiette_annuelle > self.bareme_caf.plafond:
            self.assiette_annuelle = self.bareme_caf.plafond
        elif self.assiette_annuelle < self.bareme_caf.plancher:
            self.assiette_annuelle = self.bareme_caf.plancher

        self.assiette_mensuelle = self.assiette_annuelle / 12

        self.taux_horaire = 10.0/200 # 0.05 !

        self.enfants_a_charge = 1
        self.enfants_en_creche = 1
        for frere_soeur in inscrit.freres_soeurs:
            if frere_soeur.naissance and frere_soeur.naissance <= self.debut:
                self.enfants_a_charge += 1
                if frere_soeur.entree and frere_soeur.entree <= self.debut and (frere_soeur.sortie is None or frere_soeur.sortie > self.debut):
                    self.enfants_en_creche += 1

        if self.enfants_en_creche > 1:
            self.mode_taux_horaire = u'%d enfants en crèche' % self.enfants_en_creche
            self.taux_horaire = 5.55/200 # 0.02 !
        else:
            self.mode_taux_horaire = u'%d enfants à charge' % self.enfants_a_charge
            if self.enfants_a_charge > 3:
                self.taux_horaire = 5.55/200 # 0.02 !
            elif self.enfants_a_charge == 3:
                self.taux_horaire = 6.25/200 # 0.03 !
            elif self.enfants_a_charge == 2:
                self.taux_horaire = 8.33/200 # 0.04 !
            else:
                self.mode_taux_horaire = u'1 enfant à charge'
                self.taux_horaire = 10.0/200 # 0.05 !

        self.heures_garde = jours_garde * 40
        if jours_garde == 5:
            self.mode_heures_garde = u'plein temps'
        else:
            self.mode_heures_garde = u'%d/5èmes' % jours_garde

        self.montant_heure_garde = self.assiette_mensuelle * self.taux_horaire / 100
        self.cotisation_mensuelle = self.assiette_mensuelle * self.taux_horaire * self.heures_garde * creche.mois_payes / 12 / 100

        self.montant_jour_maladie_deduit = self.assiette_mensuelle * self.taux_horaire / 10

        if self.heures_garde < 200:
            self.montant_jour_supplementaire = self.montant_jour_maladie_deduit
        else:
            self.montant_jour_supplementaire = 0

        self.total_semaine = 0
        for j in range(5):
            if self.inscription.periode_reference[j][0] == 1: self.total_semaine += 4
            if self.inscription.periode_reference[j][1] == 1: self.total_semaine += 2
            if self.inscription.periode_reference[j][2] == 1: self.total_semaine += 4

        self.total_mois = 4 * self.total_semaine
        self.total_annee = 48 * self.total_semaine
        if self.inscription.mode == 0:
            self.cout_horaire = self.cotisation_mensuelle / self.total_mois
        else:
            self.cout_horaire = 0

    def __cmp__(self, context2):
        return context2 == None or \
               self.cotisation_mensuelle != context2.cotisation_mensuelle or \
               self.total_mois != context2.total_mois or \
               self.bureau != context2.bureau or \
               self.assiette_annuelle != context2.assiette_annuelle