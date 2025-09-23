from sqlalchemy import Column, Integer, String, Float, ForeignKey
from sqlalchemy.orm import relationship
from .database import Base

class Sample(Base):
    __tablename__ = "samples"
    id = Column(Integer, primary_key=True, index=True)
    sample_id = Column(String, index=True, nullable=True)
    collection_date = Column(String, nullable=True)
    lab_name = Column(String, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    metadata_json = Column(String, nullable=True)
    file_path = Column(String, nullable=False)

    metals = relationship("MetalConcentration", back_populates="sample", cascade="all,delete-orphan")

class MetalConcentration(Base):
    __tablename__ = "metal_concentrations"
    id = Column(Integer, primary_key=True, index=True)
    sample_id = Column(Integer, ForeignKey("samples.id"), index=True, nullable=False)
    metal = Column(String, index=True, nullable=False)
    value_mg_l = Column(Float, nullable=True)

    sample = relationship("Sample", back_populates="metals")
